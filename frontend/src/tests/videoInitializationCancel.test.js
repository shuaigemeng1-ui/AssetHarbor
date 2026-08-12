// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createVideoUpload: vi.fn(),
  cancelVideoUpload: vi.fn(),
  getToken: vi.fn(() => 'original-user-token'),
}))

vi.mock('../api', () => ({
  ...api,
  completeVideoUpload: vi.fn(),
  getVideoUpload: vi.fn(),
  uploadVideoPart: vi.fn(),
}))

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
  resetVideoUploads,
  videoUploadState,
} from '../stores/videoUploads'

describe('cancelling video initialization', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    resetVideoUploads()
    await initializeVideoUploads(7)
  })

  it('waits for the original POST and deletes exactly the returned session', async () => {
    let resolveInitialization
    let initializationSignal
    api.createVideoUpload.mockImplementationOnce((_payload, { signal }) => {
      initializationSignal = signal
      return new Promise(resolve => { resolveInitialization = resolve })
    })
    api.cancelVideoUpload.mockResolvedValue(undefined)

    const file = new File(['container'], 'movie.mp4', { type: 'video/mp4' })
    const [{ task }] = addVideoFiles([file])
    await vi.waitFor(() => expect(api.createVideoUpload).toHaveBeenCalledTimes(1))

    const cancellation = cancelVideoTask(task)
    expect(task.status).toBe('cancelling')
    expect(initializationSignal.aborted).toBe(false)
    expect(api.createVideoUpload).toHaveBeenCalledTimes(1)

    resolveInitialization({ upload_id: 'original-server-session' })
    await cancellation

    expect(api.createVideoUpload).toHaveBeenCalledTimes(1)
    expect(api.cancelVideoUpload).toHaveBeenCalledWith('original-server-session', {
      token: 'original-user-token',
      suppressUnauthorized: true,
    })
    expect(videoUploadState.tasks).not.toContain(task)
  })

  it('cleans up a late initialization response after switching owners', async () => {
    let resolveOldInitialization
    let oldInitializationSignal
    api.createVideoUpload.mockImplementationOnce((_payload, { signal }) => {
      oldInitializationSignal = signal
      return new Promise(resolve => { resolveOldInitialization = resolve })
    })
    api.cancelVideoUpload.mockResolvedValue(undefined)

    const file = new File(['old-account-container'], 'old.mp4', { type: 'video/mp4' })
    const [{ task: oldTask }] = addVideoFiles([file])
    await vi.waitFor(() => expect(api.createVideoUpload).toHaveBeenCalledTimes(1))
    const oldInitialization = oldTask.initializationPromise

    await initializeVideoUploads(8)
    expect(oldInitializationSignal.aborted).toBe(false)
    expect(videoUploadState.tasks).not.toContain(oldTask)

    resolveOldInitialization({ upload_id: 'late-old-account-session' })
    await oldInitialization

    expect(api.cancelVideoUpload).toHaveBeenCalledWith('late-old-account-session', {
      token: 'original-user-token',
      suppressUnauthorized: true,
    })
    expect(videoUploadState.tasks).not.toContain(oldTask)
  })
})
