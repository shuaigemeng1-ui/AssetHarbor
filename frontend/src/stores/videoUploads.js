import { computed, reactive } from 'vue'
import {
  cancelVideoUpload,
  completeVideoUpload,
  createVideoUpload,
  getToken,
  getVideoUpload,
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

export const videoUploadState = reactive({
  tasks: [],
  restored: false,
  online: typeof navigator === 'undefined' ? true : navigator.onLine,
})

export const activeVideoUploadCount = computed(() => videoUploadState.tasks.filter(task => (
  !['completed', 'cancelled'].includes(task.status)
)).length)

const labels = {
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
    visibility: 'private',
    teamId: null,
    fingerprint: '',
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
    initController: null,
    initializationPromise: null,
    speed: 0,
    eta: Infinity,
    runStartedAt: 0,
    runBaseBytes: 0,
    ...values,
  })
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
  task.chunkSize = Number(session.chunk_size || task.chunkSize)
  task.totalParts = Number(session.total_parts || task.totalParts)
  task.uploadedParts = normalizeUploadedParts(session.uploaded_parts)
  task.expiresAt = session.expires_at || task.expiresAt
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
  ownerId = userId
  initializedOwnerId = userId
  const records = await listPersistedUploads(userId)
  if (generation !== sessionGeneration || ownerId !== userId) return
  const restoredTasks = []
  for (const record of records) {
    const task = makeTask({
      ...record,
      ownerId: userId,
      status: 'waiting_file',
      error: '',
    })
    videoUploadState.tasks.push(task)
    restoredTasks.push(task)
  }
  await Promise.all(restoredTasks.map(task => validateRestoredTask(task, generation)))
  if (generation !== sessionGeneration || ownerId !== userId) return
  videoUploadState.restored = true
  maybeInitializeTasks()
}

export function resetVideoUploads() {
  sessionGeneration++
  for (const task of videoUploadState.tasks) {
    task.status = 'cancelled'
    // Do not abort an initialization POST here. It may already be executing on
    // the server; allowing its response to arrive lets initializeTask delete
    // the exact session with the original account token captured above.
    abortTaskJobs(task)
  }
  videoUploadState.tasks.splice(0)
  ownerId = null
  initializedOwnerId = null
  initializingCount = 0
  videoUploadState.restored = false
}

function isCurrentTask(task, generation = sessionGeneration) {
  return generation === sessionGeneration
    && task.ownerId === ownerId
    && videoUploadState.tasks.includes(task)
}

async function validateRestoredTask(task, generation) {
  try {
    const session = await getVideoUpload(task.uploadId)
    if (!isCurrentTask(task, generation)) return
    applySession(task, session)
    if (session.status === 'completed' && session.video) {
      await markCompleted(task, session.video)
      return
    }
    saveTask(task)
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

export function addVideoFiles(files, { name = '', visibility = 'private', teamId = null } = {}) {
  const accepted = []
  for (const file of Array.from(files || [])) {
    if (!VIDEO_EXTENSION_RE.test(file.name) && !file.type.startsWith('video/')) {
      accepted.push({ file, error: '不支持此视频格式' })
      continue
    }
    const task = makeTask({
      ownerId,
      file,
      filename: file.name,
      size: file.size,
      name,
      visibility,
      teamId,
      status: 'queued',
    })
    videoUploadState.tasks.unshift(task)
    accepted.push({ file, task })
  }
  maybeInitializeTasks()
  return accepted
}

function unfinishedServerSessions() {
  return videoUploadState.tasks.filter(task => task.uploadId && !['completed', 'cancelled'].includes(task.status)).length
}

function maybeInitializeTasks() {
  if (!videoUploadState.online) return
  let capacity = 3 - unfinishedServerSessions() - initializingCount
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

async function initializeTask(task) {
  const generation = sessionGeneration
  const authToken = getToken()
  const controller = new AbortController()
  task.initController = controller
  task.status = 'initializing'
  task.error = ''
  try {
    task.fingerprint = await videoFingerprint(task.file)
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
      // Active cancellation deliberately waits for this original POST. Deleting
      // the exact returned id avoids racing a second initialization request.
      if (task.status === 'cancelling' && generation === sessionGeneration) {
        task.uploadId = session.upload_id
      }
      await deleteInitializationSession(session.upload_id, authToken)
      task.uploadId = null
      return
    }
    applySession(task, session)
    if (session.status === 'completed' && session.video) {
      await markCompleted(task, session.video)
      return
    }
    task.status = 'uploading'
    resetMetrics(task)
    saveTask(task)
    pumpChunks()
  } catch (error) {
    const wasCancelled = ['cancelled', 'cancelling'].includes(task.status)
      || !isCurrentTask(task, generation)
      || error.name === 'AbortError'
    if (wasCancelled) return
    task.status = 'failed'
    task.error = error.message
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
  if (!videoUploadState.online) return
  while (activeJobs.size < MAX_CONCURRENT_PARTS) {
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
    task.error = ''
    task.status = 'uploading'
    saveTask(task)
  } catch (error) {
    if (!isCurrentTask(task, generation)) return
    if (error.aborted || ['manual_paused', 'network_paused', 'cancelled'].includes(task.status)) return
    if (!navigator.onLine || error.status === 0) {
      task.status = 'network_paused'
      task.error = ''
      saveTask(task)
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
      task.error = error.message
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

async function reconcileTask(task) {
  if (!task.uploadId) return false
  try {
    const session = await getVideoUpload(task.uploadId)
    applySession(task, session)
    if (session.status === 'completed' && session.video) {
      await markCompleted(task, session.video)
      return true
    }
    saveTask(task)
    return false
  } catch (error) {
    if (error.status === 404 || error.status === 410) {
      await removePersistedUpload(persistenceKey(task))
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
  task.filename = file.name
  await resumeVideoTask(task)
}

export async function retryVideoTask(task) {
  task.partRetries = {}
  task.retryAt = {}
  await resumeVideoTask(task)
}

export async function cancelVideoTask(task) {
  task.status = 'cancelling'
  abortTaskJobs(task)
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
