// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  cancelVideoUpload: vi.fn(async () => {}),
  completeVideoUpload: vi.fn(async () => ({ code: 'video-code', media_kind: 'video' })),
  createVideoUpload: vi.fn(),
  getToken: vi.fn(() => 'session-token'),
  getVideoUpload: vi.fn(),
  listVideoUploads: vi.fn(),
  uploadVideoPart: vi.fn(),
}))

vi.mock('../api', () => api)
vi.mock('../utils/videoFingerprint', () => ({
  videoFingerprint: vi.fn(async () => 'a'.repeat(64)),
  sha256Blob: vi.fn(async () => 'b'.repeat(64)),
}))
vi.mock('../stores/uploadPersistence', () => ({
  listPersistedUploads: vi.fn(async () => []),
  persistUpload: vi.fn(async () => {}),
  removePersistedUpload: vi.fn(async () => {}),
}))

import {
  addVideoFiles,
  cancelVideoTask,
  initializeVideoUploads,
  pauseVideoTask,
  resetVideoUploads,
  videoUploadState,
} from '../stores/videoUploads'

function session(overrides = {}) {
  return {
    upload_id: 'upload-1',
    filename: 'movie.mp4',
    size: 4,
    name: 'movie.mp4',
    visibility: 'public',
    fingerprint: 'a'.repeat(64),
    team_id: null,
    chunk_size: 2,
    total_parts: 2,
    status: 'active',
    uploaded_parts: [],
    expires_at: '2026-08-20T10:00:00Z',
    video: null,
    ...overrides,
  }
}

async function settlePromises(turns = 30) {
  for (let index = 0; index < turns; index++) await Promise.resolve()
}

async function reachRateLimit() {
  const file = new File(['abcd'], 'movie.mp4', { type: 'video/mp4' })
  const [{ task }] = addVideoFiles([file])
  await vi.advanceTimersByTimeAsync(0)
  await settlePromises()
  expect(api.uploadVideoPart).toHaveBeenCalledTimes(1)
  expect(task.status).toBe('retrying')
  return task
}

describe('video part Retry-After recovery', () => {
  beforeEach(async () => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    api.listVideoUploads.mockResolvedValue({
      items: [], total: 0, max_active: 3, part_concurrency: 1,
    })
    api.createVideoUpload.mockResolvedValue(session())
    api.getVideoUpload.mockResolvedValue(session())
    api.uploadVideoPart
      .mockImplementationOnce(() => ({
        promise: Promise.reject(Object.assign(new Error('too many requests'), {
          status: 429,
          retryAfter: '1',
          retryAfterMs: 1000,
        })),
        abort: vi.fn(),
      }))
      .mockImplementation(() => ({ promise: Promise.resolve({}), abort: vi.fn() }))
    resetVideoUploads()
    videoUploadState.online = true
    await initializeVideoUploads(7)
  })

  afterEach(() => {
    resetVideoUploads()
    videoUploadState.online = true
    vi.useRealTimers()
  })

  it('gates the account, reconciles after Retry-After, and finishes without spending retry budget', async () => {
    const task = await reachRateLimit()

    expect(task.error).toContain('等待 1 秒')
    expect(task.partRetries[0]).toBeUndefined()
    await vi.advanceTimersByTimeAsync(999)
    await settlePromises()
    expect(api.uploadVideoPart).toHaveBeenCalledTimes(1)
    expect(api.getVideoUpload).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    await settlePromises(60)

    expect(api.getVideoUpload).toHaveBeenCalledWith('upload-1', {
      signal: expect.any(AbortSignal),
    })
    expect(api.uploadVideoPart).toHaveBeenCalledTimes(3)
    expect(api.completeVideoUpload).toHaveBeenCalledWith('upload-1')
    expect(task.status).toBe('completed')
  })

  it('holds every upload task owned by the rate-limited account', async () => {
    await reachRateLimit()
    const second = {
      localId: 999,
      ownerId: 7,
      uploadId: 'upload-2',
      file: new File(['xy'], 'second.mp4', { type: 'video/mp4' }),
      filename: 'second.mp4',
      size: 2,
      name: 'second.mp4',
      visibility: 'public',
      teamId: null,
      fingerprint: 'c'.repeat(64),
      serverStatus: 'active',
      chunkSize: 2,
      totalParts: 1,
      uploadedParts: [],
      expiresAt: '2026-08-20T10:00:00Z',
      status: 'uploading',
      result: null,
      error: '',
      chunkProgress: {},
      partRetries: {},
      retryAt: {},
      speed: 0,
      eta: Infinity,
      runStartedAt: 0,
      runBaseBytes: 0,
    }
    videoUploadState.tasks.push(second)
    api.getVideoUpload.mockImplementation(uploadId => Promise.resolve(session(uploadId === 'upload-2'
      ? { upload_id: 'upload-2', filename: 'second.mp4', name: 'second.mp4', size: 2, chunk_size: 2, total_parts: 1 }
      : {})))

    await vi.advanceTimersByTimeAsync(999)
    await settlePromises()
    expect(api.uploadVideoPart).not.toHaveBeenCalledWith('upload-2', expect.anything(), expect.anything(), expect.anything())

    await vi.advanceTimersByTimeAsync(1)
    await settlePromises(80)

    expect(api.uploadVideoPart).toHaveBeenCalledWith('upload-2', 0, expect.any(Blob), expect.any(Object))
    expect(second.status).toBe('completed')
  })

  it('cancels the pending Retry-After recovery with the upload task', async () => {
    const task = await reachRateLimit()

    await cancelVideoTask(task)
    await vi.advanceTimersByTimeAsync(1000)
    await settlePromises()

    expect(api.getVideoUpload).not.toHaveBeenCalled()
    expect(api.cancelVideoUpload).toHaveBeenCalledWith('upload-1')
    expect(videoUploadState.tasks).not.toContain(task)
  })

  it('cancels an old account recovery when the session generation changes', async () => {
    await reachRateLimit()

    await initializeVideoUploads(8)
    await vi.advanceTimersByTimeAsync(1000)
    await settlePromises()

    expect(api.getVideoUpload).not.toHaveBeenCalled()
    expect(videoUploadState.tasks).toHaveLength(0)
  })

  it('aborts an in-progress reconciliation when the task is cancelled', async () => {
    const task = await reachRateLimit()
    let recoverySignal
    api.getVideoUpload.mockImplementationOnce((_uploadId, { signal }) => new Promise((_resolve, reject) => {
      recoverySignal = signal
      signal.addEventListener('abort', () => {
        reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
      })
    }))

    await vi.advanceTimersByTimeAsync(1000)
    await settlePromises()
    expect(recoverySignal.aborted).toBe(false)

    await cancelVideoTask(task)
    await settlePromises()

    expect(recoverySignal.aborted).toBe(true)
    expect(videoUploadState.tasks).not.toContain(task)
  })

  it('does not revive a cancelled task while another task keeps the shared gate active', async () => {
    const file = new File(['abcd'], 'movie.mp4', { type: 'video/mp4' })
    const [{ task }] = addVideoFiles([file])
    const second = {
      localId: 998,
      ownerId: 7,
      uploadId: 'upload-2',
      file: new File(['xy'], 'second.mp4', { type: 'video/mp4' }),
      filename: 'second.mp4',
      size: 2,
      name: 'second.mp4',
      visibility: 'public',
      teamId: null,
      fingerprint: 'c'.repeat(64),
      serverStatus: 'active',
      chunkSize: 2,
      totalParts: 1,
      uploadedParts: [],
      expiresAt: '2026-08-20T10:00:00Z',
      status: 'uploading',
      result: null,
      error: '',
      chunkProgress: {},
      partRetries: {},
      retryAt: {},
      rateLimitGateId: null,
      speed: 0,
      eta: Infinity,
      runStartedAt: 0,
      runBaseBytes: 0,
    }
    videoUploadState.tasks.push(second)
    await vi.advanceTimersByTimeAsync(0)
    await settlePromises()
    expect(task.status).toBe('retrying')
    expect(second.status).toBe('retrying')

    let resolveRecovery
    api.getVideoUpload.mockImplementation(uploadId => Promise.resolve(session(uploadId === 'upload-2'
      ? { upload_id: 'upload-2', filename: 'second.mp4', name: 'second.mp4', size: 2, chunk_size: 2, total_parts: 1 }
      : {})))
    api.getVideoUpload.mockImplementationOnce((_uploadId, { signal }) => new Promise(resolve => {
      resolveRecovery = resolve
      // Deliberately resolve after abort to model a stale transport callback.
      signal.addEventListener('abort', () => {})
    }))
    await vi.advanceTimersByTimeAsync(1000)
    await settlePromises()
    const callsBeforeCancel = api.uploadVideoPart.mock.calls.filter(([uploadId]) => uploadId === task.uploadId).length

    await cancelVideoTask(task)
    resolveRecovery(session())
    await settlePromises(80)

    expect(videoUploadState.tasks).not.toContain(task)
    expect(api.uploadVideoPart.mock.calls.filter(([uploadId]) => uploadId === 'upload-1')).toHaveLength(callsBeforeCancel)
    expect(second.status).toBe('completed')
  })

  it('keeps a manual pause when a pending reconciliation responds later', async () => {
    const task = await reachRateLimit()
    let resolveRecovery
    let recoverySignal
    api.getVideoUpload.mockImplementationOnce((_uploadId, { signal }) => new Promise(resolve => {
      resolveRecovery = resolve
      recoverySignal = signal
    }))

    await vi.advanceTimersByTimeAsync(1000)
    await settlePromises()
    pauseVideoTask(task)
    resolveRecovery(session())
    await settlePromises()

    expect(recoverySignal.aborted).toBe(true)
    expect(task.status).toBe('manual_paused')
    expect(api.uploadVideoPart).toHaveBeenCalledTimes(1)
  })

  it('keeps a network pause when a pending reconciliation responds later', async () => {
    const task = await reachRateLimit()
    let resolveRecovery
    let recoverySignal
    api.getVideoUpload.mockImplementationOnce((_uploadId, { signal }) => new Promise(resolve => {
      resolveRecovery = resolve
      recoverySignal = signal
    }))

    await vi.advanceTimersByTimeAsync(1000)
    await settlePromises()
    window.dispatchEvent(new Event('offline'))
    resolveRecovery(session())
    await settlePromises()

    expect(recoverySignal.aborted).toBe(true)
    expect(task.status).toBe('network_paused')
    expect(api.uploadVideoPart).toHaveBeenCalledTimes(1)
  })
})
