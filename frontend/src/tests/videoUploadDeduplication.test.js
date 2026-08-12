// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createVideoUpload: vi.fn(() => new Promise(() => {})),
  getToken: vi.fn(() => 'token'),
  listVideoUploads: vi.fn(async () => ({ items: [], total: 0 })),
  cancelVideoUpload: vi.fn(),
  completeVideoUpload: vi.fn(),
  getVideoUpload: vi.fn(),
  uploadVideoPart: vi.fn(),
}))
const fingerprints = vi.hoisted(() => ({
  videoFingerprint: vi.fn(),
  sha256Blob: vi.fn(async () => 'b'.repeat(64)),
}))

vi.mock('../api', () => ({
  ...api,
}))
vi.mock('../utils/videoFingerprint', () => fingerprints)
vi.mock('../stores/uploadPersistence', () => ({
  listPersistedUploads: vi.fn(async () => []),
  persistUpload: vi.fn(async () => {}),
  removePersistedUpload: vi.fn(async () => {}),
}))

import {
  addVideoFiles,
  initializeVideoUploads,
  resetVideoUploads,
  shouldRetryUploadError,
  videoUploadState,
} from '../stores/videoUploads'

describe('video upload deduplication and retry classification', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    api.createVideoUpload.mockImplementation(() => new Promise(() => {}))
    api.uploadVideoPart.mockImplementation(() => ({
      promise: new Promise(() => {}),
      abort: vi.fn(),
    }))
    fingerprints.videoFingerprint.mockReset().mockResolvedValue('a'.repeat(64))
    resetVideoUploads()
    await initializeVideoUploads(7)
  })

  it('deduplicates the same File object immediately only when its upload context matches', async () => {
    const file = new File(['video'], 'movie.mp4', { type: 'video/mp4', lastModified: 123 })
    const first = addVideoFiles([file], { name: '成片', visibility: 'private', teamId: 4 })[0]
    const duplicate = addVideoFiles([file], { name: '成片', visibility: 'private', teamId: 4 })[0]
    const otherContext = addVideoFiles([file], { name: '公开成片', visibility: 'public', teamId: 4 })[0]

    expect(duplicate.duplicate).toBe(true)
    expect(duplicate.task).toBe(first.task)
    expect(otherContext.task).not.toBe(first.task)
    await vi.waitFor(() => expect(api.createVideoUpload).toHaveBeenCalledTimes(2))
    expect(videoUploadState.tasks).toHaveLength(2)
  })

  it('keeps distinct content with identical browser metadata as separate uploads', async () => {
    let resolveFirst
    let resolveSecond
    fingerprints.videoFingerprint
      .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveSecond = resolve }))

    const first = new File(['AAAA'], 'same.mp4', { type: 'video/mp4', lastModified: 123 })
    const second = new File(['BBBB'], 'same.mp4', { type: 'video/mp4', lastModified: 123 })
    addVideoFiles([first, second], { name: '成片', visibility: 'private', teamId: 4 })

    // Resolve in reverse order to exercise the asynchronous race.
    resolveSecond('2'.repeat(64))
    resolveFirst('1'.repeat(64))

    await vi.waitFor(() => expect(api.createVideoUpload).toHaveBeenCalledTimes(2))
    expect(videoUploadState.tasks).toHaveLength(2)
  })

  it('collapses same-content File copies before a second server session is initialized', async () => {
    let resolveFirst
    let resolveSecond
    fingerprints.videoFingerprint
      .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveSecond = resolve }))

    const first = new File(['SAME'], 'copy.mp4', { type: 'video/mp4', lastModified: 123 })
    const second = new File(['SAME'], 'copy.mp4', { type: 'video/mp4', lastModified: 123 })
    const results = addVideoFiles([first, second], { name: '成片', visibility: 'private', teamId: 4 })

    resolveSecond('f'.repeat(64))
    resolveFirst('f'.repeat(64))

    await vi.waitFor(() => expect(videoUploadState.tasks).toHaveLength(1))
    expect(api.createVideoUpload).toHaveBeenCalledTimes(1)
    expect(results[1].duplicate).toBe(true)
    expect(results[1].task).toBe(results[0].task)
  })

  it('keeps an unnamed initialized task canonical after the server normalizes its name', async () => {
    const file = new File(['SAME'], 'movie.mp4', { type: 'video/mp4' })
    api.createVideoUpload.mockResolvedValueOnce({
      upload_id: 'shared-upload', filename: 'movie.mp4', size: file.size,
      name: 'movie.mp4', visibility: 'private', fingerprint: 'a'.repeat(64),
      team_id: null, chunk_size: file.size, total_parts: 1, status: 'active',
      uploaded_parts: [], expires_at: '2026-08-19T10:00:00Z', video: null,
    })

    addVideoFiles([file], { name: '', visibility: 'private', teamId: null })
    await vi.waitFor(() => expect(videoUploadState.tasks[0]?.uploadId).toBe('shared-upload'))

    const duplicate = addVideoFiles([file], { name: '', visibility: 'private', teamId: null })[0]

    expect(duplicate.duplicate).toBe(true)
    expect(videoUploadState.tasks).toHaveLength(1)
    expect(api.createVideoUpload).toHaveBeenCalledTimes(1)
  })

  it('serializes separate admission batches when newer fingerprints finish first', async () => {
    let resolveFirst
    let resolveSecond
    fingerprints.videoFingerprint
      .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveSecond = resolve }))

    const first = new File(['SAME'], 'batch.mp4', { type: 'video/mp4' })
    const second = new File(['SAME'], 'batch.mp4', { type: 'video/mp4' })
    addVideoFiles([first], { name: '', visibility: 'private', teamId: null })
    await new Promise(resolve => window.setTimeout(resolve, 0))
    const secondResult = addVideoFiles([second], { name: '', visibility: 'private', teamId: null })[0]

    resolveSecond('f'.repeat(64))
    await new Promise(resolve => window.setTimeout(resolve, 0))
    expect(api.createVideoUpload).not.toHaveBeenCalled()

    resolveFirst('f'.repeat(64))
    await vi.waitFor(() => expect(api.createVideoUpload).toHaveBeenCalledTimes(1))
    expect(videoUploadState.tasks).toHaveLength(1)
    expect(secondResult.duplicate).toBe(true)
  })

  it('merges local tasks when idempotent initialization returns the same upload id', async () => {
    const session = {
      upload_id: 'canonical-upload', filename: 'movie.mp4', size: 4,
      name: '成片 A', visibility: 'private', fingerprint: 'a'.repeat(64),
      team_id: null, chunk_size: 4, total_parts: 1, status: 'active',
      uploaded_parts: [], expires_at: '2026-08-19T10:00:00Z', video: null,
    }
    api.createVideoUpload.mockResolvedValue(session)
    const first = new File(['AAAA'], 'movie.mp4', { type: 'video/mp4' })
    const second = new File(['BBBB'], 'movie.mp4', { type: 'video/mp4' })
    fingerprints.videoFingerprint
      .mockResolvedValueOnce('1'.repeat(64))
      .mockResolvedValueOnce('2'.repeat(64))

    addVideoFiles([first], { name: '成片 A', visibility: 'private' })
    addVideoFiles([second], { name: '成片 B', visibility: 'private' })

    await vi.waitFor(() => expect(api.createVideoUpload).toHaveBeenCalledTimes(2))
    await vi.waitFor(() => expect(videoUploadState.tasks).toHaveLength(1))
    expect(videoUploadState.tasks[0].uploadId).toBe('canonical-upload')
  })

  it('retries transient failures but fails fast for deterministic client errors', () => {
    expect(shouldRetryUploadError({ status: 0 })).toBe(true)
    expect(shouldRetryUploadError({ status: 408 })).toBe(true)
    expect(shouldRetryUploadError({ status: 429 })).toBe(true)
    expect(shouldRetryUploadError({ status: 507 })).toBe(true)
    expect(shouldRetryUploadError({ status: 503 })).toBe(true)
    expect(shouldRetryUploadError({ status: 400 })).toBe(false)
    expect(shouldRetryUploadError({ status: 413 })).toBe(false)
    expect(shouldRetryUploadError({ status: 422 })).toBe(false)
  })

  it('rejects an oversized video before fingerprinting or creating a server session', () => {
    const file = new File(['x'], 'large.mp4', { type: 'video/mp4' })
    Object.defineProperty(file, 'size', { value: 11 * 1024 * 1024 })

    const [result] = addVideoFiles([file], { maxSize: 10 * 1024 * 1024 })

    expect(result.error).toContain('10 MB')
    expect(fingerprints.videoFingerprint).not.toHaveBeenCalled()
    expect(api.createVideoUpload).not.toHaveBeenCalled()
    expect(videoUploadState.tasks).toHaveLength(0)
  })
})
