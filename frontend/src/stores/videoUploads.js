import { computed, reactive } from 'vue'
import {
  cancelVideoUpload,
  completeVideoUpload,
  createVideoUpload,
  getToken,
  getVideoUpload,
  listVideoUploads,
  uploadVideoPart,
} from '../api'
import { sha256Blob, videoFingerprint } from '../utils/videoFingerprint'
import { listPersistedUploads, persistUpload, removePersistedUpload } from './uploadPersistence'

export const VIDEO_ACCEPT = '.mp4,.m4v,.mov,.webm,.mkv,.avi,.mpeg,.mpg,.ts,.ogv,.ogg,.3gp,.flv,.wmv,video/*'
export const VIDEO_EXTENSION_RE = /\.(mp4|m4v|mov|webm|mkv|avi|mpeg|mpg|ts|ogv|ogg|3gp|flv|wmv)$/i
export const MAX_CONCURRENT_PARTS = 3

let ownerId = null
let initializedOwnerId = null
let nextLocalId = 1
let initializingCount = 0
let listenersInstalled = false
let roundRobinIndex = 0
let sessionGeneration = 0
const activeJobs = new Map()
const retryTimers = new Map()
let partRateLimitGate = null
let nextPartRateLimitGateId = 1
const fingerprintJobs = new Map()
const admissionBatches = new Map()
let openAdmissionBatch = null
let nextAdmissionId = 1
let admissionTail = Promise.resolve()

export const videoUploadState = reactive({
  tasks: [],
  restored: false,
  online: typeof navigator === 'undefined' ? true : navigator.onLine,
  maxActiveSessions: 3,
  maxConcurrentParts: MAX_CONCURRENT_PARTS,
})

export const activeVideoUploadCount = computed(() => videoUploadState.tasks.filter(task => (
  !['completed', 'cancelled'].includes(task.status)
)).length)

const labels = {
  checking: '正在检查文件',
  queued: '排队等待',
  initializing: '正在初始化',
  uploading: '上传中',
  network_paused: '网络中断，已暂停',
  manual_paused: '已手动暂停',
  retrying: '分片重试中',
  finalizing: '服务端校验中',
  completed: '上传完成',
  failed: '上传失败',
  waiting_file: '等待重新选择文件',
  cancelling: '正在取消',
}

export function uploadStatusLabel(task) {
  return labels[task.status] || task.status
}

function makeTask(values) {
  return reactive({
    localId: nextLocalId++,
    ownerId,
    uploadId: null,
    file: null,
    filename: '',
    size: 0,
    name: '',
    visibility: 'public',
    teamId: null,
    fingerprint: '',
    serverStatus: '',
    admissionId: null,
    chunkSize: 0,
    totalParts: 0,
    uploadedParts: [],
    expiresAt: null,
    status: 'queued',
    result: null,
    error: '',
    chunkProgress: {},
    partRetries: {},
    retryAt: {},
    rateLimitGateId: null,
    initController: null,
    initializationPromise: null,
    speed: 0,
    eta: Infinity,
    runStartedAt: 0,
    runBaseBytes: 0,
    ...values,
  })
}

function normalizeTeamId(value) {
  return value === null || value === undefined || value === '' ? null : String(value)
}

function normalizeFilename(value) {
  const tail = String(value || '').replaceAll('\\', '/').split('/').at(-1) || ''
  return tail.replaceAll('\0', '').trim().slice(0, 255) || 'video'
}

function normalizeDisplayName(name, filename) {
  return String(name || '').trim().slice(0, 255) || normalizeFilename(filename)
}

function isUnfinishedLocalTask(task) {
  return !['completed', 'cancelled', 'cancelling'].includes(task.status)
}

function sameUploadContext(task, { name, visibility, teamId, filename }) {
  return isUnfinishedLocalTask(task)
    && normalizeFilename(task.filename) === normalizeFilename(filename)
    && normalizeDisplayName(task.name, task.filename) === normalizeDisplayName(name, filename)
    && task.visibility === visibility
    && normalizeTeamId(task.teamId) === normalizeTeamId(teamId)
}

function sameFileObjectUpload(task, file, context) {
  return sameUploadContext(task, { ...context, filename: file.name }) && task.file === file
}

function sameFingerprintIdentity(task, candidate) {
  return task !== candidate
    && sameUploadContext(task, candidate)
    && task.ownerId === candidate.ownerId
    && task.size === candidate.size
    && Boolean(task.fingerprint)
    && task.fingerprint === candidate.fingerprint
}

function isRetryableHttpStatus(status) {
  return status === undefined || status === null || status === 0
    || [408, 429, 507].includes(Number(status))
    || Number(status) >= 500
}

export function shouldRetryUploadError(error) {
  return !error?.aborted && isRetryableHttpStatus(error?.status)
}

function persistenceKey(task) {
  return `${task.ownerId}:${task.uploadId}`
}

function serializableTask(task) {
  return {
    key: persistenceKey(task),
    ownerId: task.ownerId,
    uploadId: task.uploadId,
    filename: task.filename,
    size: task.size,
    name: task.name,
    visibility: task.visibility,
    teamId: task.teamId,
    fingerprint: task.fingerprint,
    chunkSize: task.chunkSize,
    totalParts: task.totalParts,
    uploadedParts: [...task.uploadedParts],
    expiresAt: task.expiresAt,
  }
}

function saveTask(task) {
  if (task.uploadId && task.ownerId != null && !['completed', 'cancelled'].includes(task.status)) {
    persistUpload(serializableTask(task))
  }
}

function normalizeUploadedParts(value) {
  if (!Array.isArray(value)) return []
  return [...new Set(value.map(part => Number(typeof part === 'object' ? part.part_number : part)))]
    .filter(Number.isInteger)
    .sort((a, b) => a - b)
}

export function applySession(task, session) {
  task.uploadId = session.upload_id || task.uploadId
  if (Object.prototype.hasOwnProperty.call(session, 'filename')) task.filename = session.filename
  if (Object.prototype.hasOwnProperty.call(session, 'size')) task.size = Number(session.size)
  if (Object.prototype.hasOwnProperty.call(session, 'name')) task.name = session.name
  if (Object.prototype.hasOwnProperty.call(session, 'visibility')) task.visibility = session.visibility
  if (Object.prototype.hasOwnProperty.call(session, 'fingerprint')) task.fingerprint = session.fingerprint
  task.chunkSize = Number(session.chunk_size || task.chunkSize)
  task.totalParts = Number(session.total_parts || task.totalParts)
  task.uploadedParts = normalizeUploadedParts(session.uploaded_parts)
  task.expiresAt = session.expires_at || task.expiresAt
  task.serverStatus = session.status || task.serverStatus
  if (Object.prototype.hasOwnProperty.call(session, 'team_id')) task.teamId = session.team_id
}

function partSize(task, partNumber) {
  const start = partNumber * task.chunkSize
  return Math.max(0, Math.min(task.chunkSize, task.size - start))
}

function confirmedBytes(task) {
  return task.uploadedParts.reduce((sum, part) => sum + partSize(task, part), 0)
}

export function taskTransferredBytes(task) {
  return Math.min(task.size, confirmedBytes(task) + Object.values(task.chunkProgress).reduce((a, b) => a + b, 0))
}

export function taskProgress(task) {
  if (!task.size) return 0
  return Math.min(100, (taskTransferredBytes(task) / task.size) * 100)
}

function resetMetrics(task) {
  task.runStartedAt = Date.now()
  task.runBaseBytes = confirmedBytes(task)
  task.speed = 0
  task.eta = Infinity
}

function updateMetrics(task) {
  const elapsed = Math.max(0.25, (Date.now() - task.runStartedAt) / 1000)
  const transferred = Math.max(0, taskTransferredBytes(task) - task.runBaseBytes)
  task.speed = transferred / elapsed
  task.eta = task.speed > 0 ? Math.max(0, (task.size - taskTransferredBytes(task)) / task.speed) : Infinity
}

function taskJobKey(task, partNumber) {
  return `${task.localId}:${partNumber}`
}

function clearPartRateLimitGate() {
  if (!partRateLimitGate) return
  const gate = partRateLimitGate
  window.clearTimeout(gate.timer)
  for (const controller of gate.controllers.values()) controller.abort()
  gate.controllers.clear()
  for (const task of videoUploadState.tasks) {
    if (task.rateLimitGateId === gate.id) task.rateLimitGateId = null
  }
  partRateLimitGate = null
}

function abortTaskRateLimitRecovery(task) {
  if (!partRateLimitGate) return
  partRateLimitGate.controllers.get(task.localId)?.abort()
  partRateLimitGate.controllers.delete(task.localId)
  task.rateLimitGateId = null
}

function partRateLimitDelay(error) {
  const serverDelay = Number(error?.retryAfterMs)
  return Number.isFinite(serverDelay) && serverDelay > 0
    ? Math.min(5 * 60 * 1000, Math.max(1000, Math.ceil(serverDelay)))
    : 60 * 1000
}

function markTaskWaitingForPartRateLimit(task, gate) {
  const until = gate.until
  const seconds = Math.max(1, Math.ceil((until - Date.now()) / 1000))
  task.rateLimitGateId = gate.id
  task.status = 'retrying'
  task.error = `请求过快，服务端要求等待 ${seconds} 秒，随后将自动核对进度并继续上传`
}

function isTaskWaitingForRateLimit(task, gate) {
  return partRateLimitGate === gate
    && gate.generation === sessionGeneration
    && task.rateLimitGateId === gate.id
    && task.status === 'retrying'
    && videoUploadState.online
    && isCurrentTask(task, gate.generation)
}

function schedulePartRateLimitRecovery(error, task, generation) {
  if (!isCurrentTask(task, generation)) return
  const until = Date.now() + partRateLimitDelay(error)
  const previousGate = partRateLimitGate?.generation === generation
    ? partRateLimitGate
    : null
  const currentUntil = previousGate?.until || 0
  const waitingTasks = new Set(videoUploadState.tasks.filter(candidate => (
    isCurrentTask(candidate, generation)
    && candidate.file
    && candidate.uploadId
    && (
      ['uploading', 'retrying'].includes(candidate.status)
      || candidate.rateLimitGateId === previousGate?.id
    )
  )))
  clearPartRateLimitGate()
  const gate = {
    id: nextPartRateLimitGateId++,
    generation,
    until: Math.max(currentUntil, until),
    timer: null,
    controllers: new Map(),
  }
  partRateLimitGate = gate
  for (const candidate of waitingTasks) {
    markTaskWaitingForPartRateLimit(candidate, gate)
    saveTask(candidate)
  }
  gate.timer = window.setTimeout(() => recoverAfterPartRateLimit(gate), Math.max(0, gate.until - Date.now()))
}

async function recoverAfterPartRateLimit(gate) {
  if (partRateLimitGate !== gate || gate.generation !== sessionGeneration) return
  const tasks = videoUploadState.tasks.filter(task => (
    isCurrentTask(task, gate.generation)
    && ['uploading', 'retrying'].includes(task.status)
    && task.file
    && task.uploadId
  ))
  for (const task of tasks) {
    if (partRateLimitGate !== gate || gate.generation !== sessionGeneration) return
    if (!isTaskWaitingForRateLimit(task, gate)) continue
    const controller = new AbortController()
    gate.controllers.set(task.localId, controller)
    try {
      const complete = await reconcileTask(task, {
        signal: controller.signal,
        shouldApply: () => isTaskWaitingForRateLimit(task, gate),
      })
      if (partRateLimitGate !== gate || gate.generation !== sessionGeneration) return
      if (complete === null || !isTaskWaitingForRateLimit(task, gate)) continue
      task.rateLimitGateId = null
      if (!complete) {
        task.status = 'uploading'
        task.error = ''
        resetMetrics(task)
        saveTask(task)
      }
    } catch (error) {
      if (partRateLimitGate !== gate || gate.generation !== sessionGeneration) return
      if (!isTaskWaitingForRateLimit(task, gate)) continue
      if (error.status === 429) {
        schedulePartRateLimitRecovery(error, task, gate.generation)
        return
      }
      task.status = 'failed'
      task.error = error.message
      abortTaskJobs(task)
      saveTask(task)
    } finally {
      if (gate.controllers.get(task.localId) === controller) gate.controllers.delete(task.localId)
    }
  }
  if (partRateLimitGate !== gate || gate.generation !== sessionGeneration) return
  for (const task of videoUploadState.tasks) {
    if (task.rateLimitGateId === gate.id) task.rateLimitGateId = null
  }
  partRateLimitGate = null
  pumpChunks()
}

function abortTaskJobs(task) {
  for (const [key, job] of activeJobs) {
    if (job.task === task) {
      job.abort?.()
      activeJobs.delete(key)
    }
  }
  for (const [key, timer] of retryTimers) {
    if (key.startsWith(`${task.localId}:`)) {
      clearTimeout(timer)
      retryTimers.delete(key)
    }
  }
  task.chunkProgress = {}
}

function installNetworkListeners() {
  if (listenersInstalled || typeof window === 'undefined') return
  listenersInstalled = true
  window.addEventListener('offline', () => {
    videoUploadState.online = false
    for (const task of videoUploadState.tasks) {
      if (['uploading', 'retrying'].includes(task.status)) {
        task.status = 'network_paused'
        task.error = ''
        abortTaskRateLimitRecovery(task)
        abortTaskJobs(task)
        saveTask(task)
      }
    }
  })
  window.addEventListener('online', () => {
    videoUploadState.online = true
    for (const task of videoUploadState.tasks.filter(item => item.status === 'network_paused' && item.file)) {
      resumeVideoTask(task, true)
    }
    maybeInitializeTasks()
    pumpChunks()
  })
}

export async function initializeVideoUploads(userId) {
  installNetworkListeners()
  if (initializedOwnerId === userId) return
  resetVideoUploads()
  const generation = sessionGeneration
  const authToken = getToken()
  ownerId = userId
  initializedOwnerId = userId
  const [localResult, serverResult] = await Promise.allSettled([
    listPersistedUploads(userId),
    listVideoUploads({ token: authToken, suppressUnauthorized: true }),
  ])
  if (generation !== sessionGeneration || ownerId !== userId) return
  const records = localResult.status === 'fulfilled' ? localResult.value : []
  const restoredTasks = []
  const byUploadId = new Map()
  for (const record of records) {
    const task = makeTask({
      ...record,
      ownerId: userId,
      status: 'waiting_file',
      error: '',
    })
    videoUploadState.tasks.push(task)
    restoredTasks.push(task)
    if (task.uploadId) byUploadId.set(task.uploadId, task)
  }

  const recoveryJobs = []
  if (serverResult.status === 'fulfilled') {
    videoUploadState.maxActiveSessions = Math.max(1, Number(serverResult.value.max_active) || 3)
    videoUploadState.maxConcurrentParts = Math.min(32, Math.max(1, Number(serverResult.value.part_concurrency) || MAX_CONCURRENT_PARTS))
    for (const session of serverResult.value.items || []) {
      let task = byUploadId.get(session.upload_id)
      if (!task) {
        task = makeTask({
          ownerId: userId,
          uploadId: session.upload_id,
          filename: session.filename,
          size: Number(session.size || 0),
          name: session.name || '',
          visibility: session.visibility || 'public',
          teamId: session.team_id,
          fingerprint: session.fingerprint || '',
          status: 'waiting_file',
        })
        videoUploadState.tasks.push(task)
        restoredTasks.push(task)
        byUploadId.set(task.uploadId, task)
      }
      recoveryJobs.push(applyRestoredSession(task, session, generation, authToken))
    }
    const discovered = new Set((serverResult.value.items || []).map(item => item.upload_id))
    for (const task of restoredTasks.filter(item => !discovered.has(item.uploadId))) {
      recoveryJobs.push(validateRestoredTask(task, generation, authToken))
    }
  } else {
    recoveryJobs.push(...restoredTasks.map(task => validateRestoredTask(task, generation, authToken)))
  }

  await Promise.all(recoveryJobs)
  if (generation !== sessionGeneration || ownerId !== userId) return
  videoUploadState.restored = true
  maybeInitializeTasks()
}

export function resetVideoUploads() {
  sessionGeneration++
  clearPartRateLimitGate()
  for (const task of videoUploadState.tasks) {
    task.status = 'cancelled'
    // Do not abort an initialization POST here. It may already be executing on
    // the server; allowing its response to arrive lets initializeTask delete
    // the exact session with the original account token captured above.
    abortTaskJobs(task)
  }
  videoUploadState.tasks.splice(0)
  fingerprintJobs.clear()
  admissionBatches.clear()
  openAdmissionBatch = null
  admissionTail = Promise.resolve()
  ownerId = null
  initializedOwnerId = null
  initializingCount = 0
  roundRobinIndex = 0
  videoUploadState.restored = false
  videoUploadState.maxActiveSessions = 3
  videoUploadState.maxConcurrentParts = MAX_CONCURRENT_PARTS
}

function isCurrentTask(task, generation = sessionGeneration) {
  return generation === sessionGeneration
    && task.ownerId === ownerId
    && videoUploadState.tasks.includes(task)
}

async function validateRestoredTask(task, generation, authToken) {
  try {
    const session = await getVideoUpload(task.uploadId, {
      token: authToken,
      suppressUnauthorized: true,
    })
    if (!isCurrentTask(task, generation)) return
    await applyRestoredSession(task, session, generation, authToken)
  } catch (error) {
    if (!isCurrentTask(task, generation)) return
    if ([404, 410].includes(error.status)) {
      await removePersistedUpload(persistenceKey(task))
      const index = videoUploadState.tasks.indexOf(task)
      if (index >= 0) videoUploadState.tasks.splice(index, 1)
      return
    }
    task.error = `暂时无法确认服务端进度：${error.message}`
  }
}

async function applyRestoredSession(task, session, generation, authToken) {
  if (!isCurrentTask(task, generation)) return
  applySession(task, session)
  if (session.status === 'completed' && session.video) {
    await markCompleted(task, session.video)
    return
  }
  if (['verifying', 'finalizing'].includes(session.status)) {
    task.status = 'finalizing'
    task.error = ''
    saveTask(task)
    await recoverRemoteFinalization(task, generation, authToken)
    return
  }
  if (session.status === 'active') {
    task.status = task.file ? 'uploading' : 'waiting_file'
    task.error = ''
  } else {
    task.status = 'failed'
    task.error = '服务端上传会话处于失败状态，可取消后重新上传'
  }
  saveTask(task)
}

async function recoverRemoteFinalization(task, generation = sessionGeneration, authToken = getToken()) {
  if (!isCurrentTask(task, generation)) return
  task.status = 'finalizing'
  task.error = ''
  try {
    const result = await completeVideoUpload(task.uploadId, {
      token: authToken,
      suppressUnauthorized: true,
    })
    if (!isCurrentTask(task, generation)) return
    await markCompleted(task, result)
  } catch (error) {
    if (!isCurrentTask(task, generation)) return
    try {
      const session = await getVideoUpload(task.uploadId, {
        token: authToken,
        suppressUnauthorized: true,
      })
      if (!isCurrentTask(task, generation)) return
      applySession(task, session)
      if (session.status === 'completed' && session.video) {
        await markCompleted(task, session.video)
        return
      }
      if (session.status === 'active') {
        task.status = task.file ? 'uploading' : 'waiting_file'
        task.error = task.file ? '' : '服务端已恢复为可续传状态，请重新选择原文件'
      } else {
        task.status = 'failed'
        task.error = `服务端校验尚未完成：${error.message}`
      }
    } catch (reconcileError) {
      if (!isCurrentTask(task, generation)) return
      task.status = 'failed'
      task.error = `恢复服务端校验失败：${reconcileError.message}`
    }
    saveTask(task)
  }
}

function currentAdmissionBatch() {
  if (openAdmissionBatch && openAdmissionBatch.generation === sessionGeneration) return openAdmissionBatch
  const batch = {
    id: nextAdmissionId++,
    generation: sessionGeneration,
    tasks: [],
    results: new Map(),
  }
  openAdmissionBatch = batch
  admissionBatches.set(batch.id, batch)
  window.setTimeout(() => {
    // Fingerprints from separate file-picker/drop events can finish out of
    // order. Commit batches in creation order so the oldest matching task is
    // always canonical before a newer batch is admitted.
    admissionTail = admissionTail
      .catch(() => {})
      .then(() => closeAdmissionBatch(batch))
  }, 0)
  return batch
}

export function addVideoFiles(files, {
  name = '',
  visibility = 'public',
  teamId = null,
  maxSize = Infinity,
} = {}) {
  const accepted = []
    const context = { name, visibility, teamId }
  for (const file of Array.from(files || [])) {
    if (!VIDEO_EXTENSION_RE.test(file.name) && !file.type.startsWith('video/')) {
      accepted.push({ file, error: '不支持此视频格式' })
      continue
    }
    if (Number.isFinite(maxSize) && file.size > maxSize) {
      accepted.push({ file, error: `文件大小超过 ${Math.round(maxSize / 1024 / 1024)} MB 限制` })
      continue
    }
    // Object identity is the only safe synchronous shortcut. Browser metadata
    // (name/size/lastModified) is not a content identity and can collide.
    const existing = videoUploadState.tasks.find(task => sameFileObjectUpload(task, file, context))
    if (existing) {
      if (!existing.file && ['waiting_file', 'failed'].includes(existing.status)) {
        attachVideoFile(existing, file).catch(() => {})
      }
      accepted.push({ file, task: existing, duplicate: true })
      continue
    }
    const batch = currentAdmissionBatch()
    const filename = normalizeFilename(file.name)
    const task = makeTask({
      ownerId,
      file,
      filename,
      size: file.size,
      name: normalizeDisplayName(name, filename),
      visibility,
      teamId,
      status: 'checking',
      admissionId: batch.id,
    })
    videoUploadState.tasks.unshift(task)
    const result = { file, task }
    accepted.push(result)
    batch.tasks.push(task)
    batch.results.set(task.localId, result)
    prepareLocalTaskFingerprint(task)
  }
  return accepted
}

function prepareLocalTaskFingerprint(task) {
  const generation = sessionGeneration
  const job = (async () => {
    try {
      const fingerprint = await videoFingerprint(task.file)
      if (!isCurrentTask(task, generation) || task.status !== 'checking') return
      task.fingerprint = fingerprint
    } catch (error) {
      if (!isCurrentTask(task, generation) || task.status !== 'checking') return
      task.status = 'failed'
      task.error = `无法读取文件指纹：${error.message}`
    }
  })()
  fingerprintJobs.set(task.localId, job)
  job.finally(() => {
    if (fingerprintJobs.get(task.localId) === job) fingerprintJobs.delete(task.localId)
  })
  return job
}

async function closeAdmissionBatch(batch) {
  if (openAdmissionBatch === batch) openAdmissionBatch = null
  const jobs = batch.tasks.map(task => fingerprintJobs.get(task.localId)).filter(Boolean)
  await Promise.allSettled(jobs)
  admissionBatches.delete(batch.id)
  if (batch.generation !== sessionGeneration) return

  const ready = batch.tasks
    .filter(task => isCurrentTask(task, batch.generation) && task.status === 'checking' && task.fingerprint)
    .sort((left, right) => left.localId - right.localId)

  for (const task of ready) {
    if (!isCurrentTask(task, batch.generation) || task.status !== 'checking') continue
    const existing = videoUploadState.tasks.find(candidate => (
      sameFingerprintIdentity(candidate, task)
      && candidate.localId < task.localId
      && (isUnfinishedLocalTask(candidate) || candidate.admissionId === batch.id)
    ))
    if (existing) {
      const result = batch.results.get(task.localId)
      if (result) {
        result.task = existing
        result.duplicate = true
      }
      const index = videoUploadState.tasks.indexOf(task)
      if (index >= 0) videoUploadState.tasks.splice(index, 1)
      if (!existing.file) {
        existing.file = task.file
        existing.filename = task.file.name
        existing.error = ''
        resumeVideoTask(existing).catch(() => {})
      }
      continue
    }
    task.status = 'queued'
  }
  maybeInitializeTasks()
}

function unfinishedServerSessions() {
  return new Set(videoUploadState.tasks
    .filter(task => task.uploadId && !['completed', 'cancelled'].includes(task.status))
    .map(task => task.uploadId)).size
}

function maybeInitializeTasks() {
  if (!videoUploadState.online) return
  let capacity = videoUploadState.maxActiveSessions - unfinishedServerSessions() - initializingCount
  for (const task of videoUploadState.tasks) {
    if (capacity <= 0) break
    if (task.status === 'queued' && task.file && !task.uploadId) {
      initializingCount++
      capacity--
      const promise = initializeTask(task)
      task.initializationPromise = promise
      promise.finally(() => {
        if (task.initializationPromise === promise) task.initializationPromise = null
      })
    }
  }
}

function taskForUploadId(uploadId, exclude = null) {
  if (!uploadId) return null
  return videoUploadState.tasks.find(candidate => (
    candidate !== exclude
    && candidate.ownerId === ownerId
    && candidate.uploadId === uploadId
    && !['completed', 'cancelled', 'cancelling'].includes(candidate.status)
  )) || null
}

function removeLocalTask(task) {
  task.status = 'cancelled'
  abortTaskJobs(task)
  const index = videoUploadState.tasks.indexOf(task)
  if (index >= 0) videoUploadState.tasks.splice(index, 1)
}

function mergeIntoCanonicalUpload(task, session) {
  const canonical = taskForUploadId(session.upload_id, task)
  if (!canonical) return null
  applySession(canonical, session)
  if (!canonical.file && task.file) canonical.file = task.file
  canonical.error = ''
  removeLocalTask(task)
  saveTask(canonical)
  return canonical
}

async function initializeTask(task) {
  const generation = sessionGeneration
  const authToken = getToken()
  const controller = new AbortController()
  task.initController = controller
  task.status = 'initializing'
  task.error = ''
  try {
    if (!task.fingerprint) task.fingerprint = await videoFingerprint(task.file)
    if (!isCurrentTask(task, generation) || ['cancelled', 'cancelling'].includes(task.status)) return
    if (!videoUploadState.online) {
      task.status = 'network_paused'
      return
    }
    const payload = {
      filename: task.filename,
      size: task.size,
      name: task.name || '',
      visibility: task.visibility,
      team_id: task.teamId,
      fingerprint: task.fingerprint,
    }
    const session = await createVideoUpload(payload, { signal: controller.signal, token: authToken })
    if (!isCurrentTask(task, generation) || ['cancelled', 'cancelling'].includes(task.status)) {
      const sharedTask = generation === sessionGeneration
        ? taskForUploadId(session.upload_id, task)
        : null
      if (sharedTask) {
        // This POST reused a session already represented by another local task.
        // Cancelling the duplicate must not delete the canonical task's server data.
        removeLocalTask(task)
        return
      }
      // Active cancellation deliberately waits for this original POST. Deleting
      // the exact returned id avoids racing a second initialization request.
      if (task.status === 'cancelling' && generation === sessionGeneration) {
        task.uploadId = session.upload_id
      }
      await deleteInitializationSession(session.upload_id, authToken)
      task.uploadId = null
      return
    }
    const canonical = mergeIntoCanonicalUpload(task, session) || task
    if (canonical === task) applySession(task, session)
    if (session.status === 'completed' && session.video) {
      await markCompleted(canonical, session.video)
      return
    }
    if (['verifying', 'finalizing'].includes(session.status)) {
      canonical.status = 'finalizing'
      saveTask(canonical)
      await recoverRemoteFinalization(canonical, generation, authToken)
      return
    }
    canonical.status = 'uploading'
    resetMetrics(canonical)
    saveTask(canonical)
    pumpChunks()
  } catch (error) {
    const wasCancelled = ['cancelled', 'cancelling'].includes(task.status)
      || !isCurrentTask(task, generation)
      || error.name === 'AbortError'
    if (wasCancelled) return
    if (isRetryableHttpStatus(error.status)) {
      task.status = 'network_paused'
      task.error = `初始化暂时失败：${error.message}，可点击继续重试`
    } else {
      task.status = 'failed'
      task.error = error.message
    }
  } finally {
    task.initController = null
    if (generation === sessionGeneration) {
      initializingCount = Math.max(0, initializingCount - 1)
      maybeInitializeTasks()
    }
  }
}

async function deleteInitializationSession(uploadId, token) {
  if (!uploadId) return
  try {
    await cancelVideoUpload(uploadId, { token, suppressUnauthorized: true })
  } catch (error) {
    if (![404, 410].includes(error.status)) throw error
  }
}

function eligibleTask(task) {
  return ['uploading', 'retrying'].includes(task.status) && task.file && task.uploadId
}

function nextPart(task) {
  const uploaded = new Set(task.uploadedParts)
  for (let part = 0; part < task.totalParts; part++) {
    const key = taskJobKey(task, part)
    if (!uploaded.has(part) && !activeJobs.has(key) && (task.retryAt[part] || 0) <= Date.now()) return part
  }
  return null
}

function nextChunkCandidate() {
  const tasks = videoUploadState.tasks.filter(eligibleTask)
  if (!tasks.length) return null
  for (let offset = 0; offset < tasks.length; offset++) {
    const index = (roundRobinIndex + offset) % tasks.length
    const task = tasks[index]
    const part = nextPart(task)
    if (part != null) {
      roundRobinIndex = (index + 1) % tasks.length
      return { task, part }
    }
  }
  return null
}

function pumpChunks() {
  if (!videoUploadState.online || partRateLimitGate) return
  while (activeJobs.size < videoUploadState.maxConcurrentParts) {
    const candidate = nextChunkCandidate()
    if (!candidate) break
    startChunk(candidate.task, candidate.part)
  }
  for (const task of videoUploadState.tasks.filter(eligibleTask)) maybeFinalize(task)
}

async function startChunk(task, partNumber) {
  const generation = sessionGeneration
  const key = taskJobKey(task, partNumber)
  const job = { task, partNumber, abort: null }
  activeJobs.set(key, job)
  task.chunkProgress[partNumber] = 0
  const start = partNumber * task.chunkSize
  const blob = task.file.slice(start, Math.min(start + task.chunkSize, task.size))
  try {
    const sha256 = await sha256Blob(blob)
    if (!isCurrentTask(task, generation) || !eligibleTask(task) || !activeJobs.has(key)) return
    const transport = uploadVideoPart(task.uploadId, partNumber, blob, {
      start,
      total: task.size,
      sha256,
      onProgress: loaded => {
        task.chunkProgress[partNumber] = loaded
        updateMetrics(task)
      },
    })
    job.abort = transport.abort
    await transport.promise
    if (!isCurrentTask(task, generation) || !eligibleTask(task)) return
    if (!task.uploadedParts.includes(partNumber)) {
      task.uploadedParts.push(partNumber)
      task.uploadedParts.sort((a, b) => a - b)
    }
    delete task.partRetries[partNumber]
    delete task.retryAt[partNumber]
    if (partRateLimitGate?.generation === generation) {
      markTaskWaitingForPartRateLimit(task, partRateLimitGate)
    } else {
      task.error = ''
      task.status = 'uploading'
    }
    saveTask(task)
  } catch (error) {
    if (!isCurrentTask(task, generation)) return
    if (error.aborted || ['manual_paused', 'network_paused', 'cancelled', 'cancelling'].includes(task.status)) return
    if (!navigator.onLine || error.status === 0) {
      task.status = 'network_paused'
      task.error = ''
      saveTask(task)
      return
    }
    let retryCause = error
    if (error.status === 409) {
      try {
        const complete = await reconcileTask(task)
        if (complete) return
        if (task.uploadedParts.includes(partNumber)) {
          task.status = 'uploading'
          task.error = ''
          return
        }
      } catch (reconcileError) {
        if (!shouldRetryUploadError(reconcileError)) {
          task.status = 'failed'
          task.error = reconcileError.message
          abortTaskJobs(task)
          saveTask(task)
          return
        }
        retryCause = reconcileError
      }
    }
    if (!shouldRetryUploadError(retryCause)) {
      task.status = 'failed'
      task.error = retryCause.message
      abortTaskJobs(task)
      saveTask(task)
      return
    }
    if (retryCause.status === 429) {
      schedulePartRateLimitRecovery(retryCause, task, generation)
      return
    }
    const attempts = (task.partRetries[partNumber] || 0) + 1
    task.partRetries[partNumber] = attempts
    if (attempts <= 3) {
      const delay = [1000, 2000, 4000][attempts - 1]
      task.status = 'retrying'
      task.error = `分片 ${partNumber + 1} 上传失败，${delay / 1000} 秒后重试（${attempts}/3）`
      task.retryAt[partNumber] = Date.now() + delay
      const timer = window.setTimeout(() => {
        retryTimers.delete(key)
        if (['uploading', 'retrying'].includes(task.status)) pumpChunks()
      }, delay)
      retryTimers.set(key, timer)
    } else {
      task.status = 'failed'
      task.error = retryCause.message
      abortTaskJobs(task)
      saveTask(task)
    }
  } finally {
    activeJobs.delete(key)
    delete task.chunkProgress[partNumber]
    if (!isCurrentTask(task, generation)) return
    updateMetrics(task)
    if (eligibleTask(task)) maybeFinalize(task)
    pumpChunks()
  }
}

async function maybeFinalize(task) {
  if (task.status === 'finalizing' || task.uploadedParts.length !== task.totalParts) return
  if ([...activeJobs.values()].some(job => job.task === task)) return
  task.status = 'finalizing'
  task.error = ''
  const generation = sessionGeneration
  try {
    const result = await completeVideoUpload(task.uploadId)
    if (!isCurrentTask(task, generation) || task.status !== 'finalizing') return
    await markCompleted(task, result)
  } catch (error) {
    if (!isCurrentTask(task, generation) || task.status !== 'finalizing') return
    task.status = 'failed'
    task.error = error.message
    saveTask(task)
  }
}

async function markCompleted(task, result) {
  task.result = result
  task.status = 'completed'
  task.uploadedParts = Array.from({ length: task.totalParts }, (_, index) => index)
  task.speed = 0
  task.eta = 0
  await removePersistedUpload(persistenceKey(task))
  window.dispatchEvent(new CustomEvent('oss:video-upload-complete', { detail: result }))
  maybeInitializeTasks()
}

async function reconcileTask(task, { signal, shouldApply } = {}) {
  if (!task.uploadId) return false
  const canApply = () => !shouldApply || shouldApply()
  try {
    const session = await getVideoUpload(task.uploadId, { signal })
    if (!canApply()) return null
    applySession(task, session)
    if (session.status === 'completed' && session.video) {
      await markCompleted(task, session.video)
      return true
    }
    saveTask(task)
    return false
  } catch (error) {
    if (error.status === 404 || error.status === 410) {
      if (!canApply()) return null
      await removePersistedUpload(persistenceKey(task))
      if (!canApply()) return null
      task.uploadId = null
      task.uploadedParts = []
      task.chunkSize = 0
      task.totalParts = 0
      task.expiresAt = null
      return false
    }
    throw error
  }
}

export function pauseVideoTask(task) {
  if (!['uploading', 'retrying'].includes(task.status)) return
  task.status = 'manual_paused'
  task.error = ''
  abortTaskRateLimitRecovery(task)
  abortTaskJobs(task)
  saveTask(task)
  pumpChunks()
}

export async function resumeVideoTask(task, fromNetwork = false) {
  if (!task.file) {
    task.status = 'waiting_file'
    return
  }
  if (!navigator.onLine) {
    task.status = 'network_paused'
    return
  }
  task.status = 'initializing'
  task.error = ''
  task.retryAt = {}
  const generation = sessionGeneration
  try {
    const complete = await reconcileTask(task)
    if (!isCurrentTask(task, generation) || task.status === 'cancelled') return
    if (complete) return
    if (!task.uploadId) {
      task.status = 'queued'
      maybeInitializeTasks()
      return
    }
    task.status = 'uploading'
    resetMetrics(task)
    pumpChunks()
  } catch (error) {
    if (!isCurrentTask(task, generation)) return
    task.status = fromNetwork ? 'network_paused' : 'failed'
    task.error = error.message
  }
}

export async function attachVideoFile(task, file) {
  const generation = sessionGeneration
  task.status = 'initializing'
  task.error = ''
  const fingerprint = await videoFingerprint(file)
  if (!isCurrentTask(task, generation) || task.status === 'cancelled') return
  if (file.size !== task.size || fingerprint !== task.fingerprint) {
    task.status = 'waiting_file'
    task.error = '所选文件与原上传任务不一致，请选择原文件'
    throw new Error(task.error)
  }
  task.file = file
  task.filename = normalizeFilename(file.name)
  await resumeVideoTask(task)
}

export async function retryVideoTask(task) {
  if (['verifying', 'finalizing'].includes(task.serverStatus) && task.uploadId) {
    await recoverRemoteFinalization(task)
    return
  }
  task.partRetries = {}
  task.retryAt = {}
  await resumeVideoTask(task)
}

export async function cancelVideoTask(task) {
  task.status = 'cancelling'
  abortTaskRateLimitRecovery(task)
  abortTaskJobs(task)
  if (partRateLimitGate && !videoUploadState.tasks.some(candidate => (
    candidate !== task
    && ['uploading', 'retrying'].includes(candidate.status)
    && candidate.file
    && candidate.uploadId
  ))) clearPartRateLimitGate()
  try {
    if (task.initializationPromise) await task.initializationPromise
    if (task.uploadId) {
      try {
        await cancelVideoUpload(task.uploadId)
      } catch (error) {
        if (![404, 410].includes(error.status)) throw error
      }
    }
    if (task.uploadId) await removePersistedUpload(persistenceKey(task))
    task.status = 'cancelled'
    const index = videoUploadState.tasks.indexOf(task)
    if (index >= 0) videoUploadState.tasks.splice(index, 1)
    maybeInitializeTasks()
    pumpChunks()
  } catch (error) {
    task.status = 'failed'
    task.error = `取消失败：${error.message}`
    throw error
  }
}

export function dismissCompletedTask(task) {
  if (task.status !== 'completed') return
  const index = videoUploadState.tasks.indexOf(task)
  if (index >= 0) videoUploadState.tasks.splice(index, 1)
}
