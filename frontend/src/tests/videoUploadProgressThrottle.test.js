// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { watch } from 'vue'

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
  initializeVideoUploads,
  resetVideoUploads,
  taskProgress,
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
    chunk_size: 4,
    total_parts: 1,
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

async function startUploading() {
  api.uploadVideoPart.mockImplementation(() => ({
    promise: new Promise(() => {}),
    abort: vi.fn(),
  }))
  const file = new File(['abcd'], 'movie.mp4', { type: 'video/mp4' })
  const [{ task }] = addVideoFiles([file])
  await vi.advanceTimersByTimeAsync(0)
  await settlePromises()
  expect(api.uploadVideoPart).toHaveBeenCalledTimes(1)
  const onProgress = api.uploadVideoPart.mock.calls[0][3].onProgress
  return { task, onProgress }
}

describe('video upload chunk progress throttling', () => {
  beforeEach(async () => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    api.listVideoUploads.mockResolvedValue({
      items: [], total: 0, max_active: 3, part_concurrency: 1,
    })
    api.createVideoUpload.mockResolvedValue(session())
    api.getVideoUpload.mockResolvedValue(session())
    resetVideoUploads()
    videoUploadState.online = true
    await initializeVideoUploads(7)
  })

  afterEach(() => {
    resetVideoUploads()
    videoUploadState.online = true
    vi.useRealTimers()
  })

  it('throttles a burst of progress events to one reactive write and one metric update', async () => {
    const { task, onProgress } = await startUploading()

    const chunkWrites = []
    const speedWrites = []
    watch(() => task.chunkProgress[0], value => chunkWrites.push(value), { flush: 'sync' })
    watch(() => task.speed, value => speedWrites.push(value), { flush: 'sync' })

    // 30 XHR progress events in the same tick (real XHRs fire dozens/sec).
    for (let index = 1; index <= 30; index++) onProgress(index)

    // Only the first event crossed the throttle window; the rest were absorbed.
    expect(chunkWrites).toHaveLength(1)
    expect(task.chunkProgress[0]).toBe(1)
    // updateMetrics ran exactly once with the first flushed value (elapsed is
    // floored at 0.25s, so transferred 1 byte => 4 B/s).
    expect(speedWrites).toHaveLength(1)
    expect(task.speed).toBe(4)

    // Once the throttle window elapses, the next event applies the newest value.
    await vi.advanceTimersByTimeAsync(250)
    onProgress(31)
    expect(chunkWrites).toHaveLength(2)
    expect(task.chunkProgress[0]).toBe(31)
  })

  it('applies the final throttled value on completion so the bar ends at 100%', async () => {
    let resolvePart
    api.uploadVideoPart.mockImplementation((_id, _part, _blob, _options) => ({
      promise: new Promise(resolve => { resolvePart = resolve }),
      abort: vi.fn(),
    }))
    const file = new File(['abcd'], 'movie.mp4', { type: 'video/mp4' })
    const [{ task }] = addVideoFiles([file])
    await vi.advanceTimersByTimeAsync(0)
    await settlePromises()
    expect(api.uploadVideoPart).toHaveBeenCalledTimes(1)
    const onProgress = api.uploadVideoPart.mock.calls[0][3].onProgress

    // A burst that never crosses the window leaves only the first value applied…
    for (let index = 1; index <= 30; index++) onProgress(index)
    expect(task.chunkProgress[0]).toBe(1)

    // …but part completion flushes the latest progress and confirms the part,
    // so the final reported progress is exactly 100%.
    resolvePart({})
    await settlePromises(60)

    expect(task.uploadedParts).toContain(0)
    expect(task.status).toBe('completed')
    expect(taskProgress(task)).toBe(100)
  })
})
