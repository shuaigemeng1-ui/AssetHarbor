// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createVideoUpload: vi.fn(() => new Promise(() => {})),
  getToken: vi.fn(() => 'token'),
}))
const fingerprints = vi.hoisted(() => ({
  videoFingerprint: vi.fn(),
  sha256Blob: vi.fn(async () => 'b'.repeat(64)),
}))

vi.mock('../api', () => ({
  ...api,
  cancelVideoUpload: vi.fn(),
  completeVideoUpload: vi.fn(),
  getVideoUpload: vi.fn(),
  uploadVideoPart: vi.fn(),
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
    await vi.waitFor(() => expect(api.createVideoUpload).toHaveBeenCalledTimes(1))
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
    await vi.waitFor(() => expect(api.createVideoUpload).toHaveBeenCalledTimes(1))
    resolveFirst('f'.repeat(64))

    await vi.waitFor(() => expect(videoUploadState.tasks).toHaveLength(1))
    expect(api.createVideoUpload).toHaveBeenCalledTimes(1)
    expect(results[0].duplicate).toBe(true)
    expect(results[0].task).toBe(results[1].task)
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
})
