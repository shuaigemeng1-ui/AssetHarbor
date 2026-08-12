// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listVideoUploads: vi.fn(),
  getVideoUpload: vi.fn(),
  completeVideoUpload: vi.fn(),
  getToken: vi.fn(() => 'session-token'),
}))
const persistence = vi.hoisted(() => ({
  listPersistedUploads: vi.fn(async () => []),
  persistUpload: vi.fn(async () => {}),
  removePersistedUpload: vi.fn(async () => {}),
}))

vi.mock('../api', () => ({
  ...api,
  cancelVideoUpload: vi.fn(),
  createVideoUpload: vi.fn(),
  uploadVideoPart: vi.fn(),
}))
vi.mock('../utils/videoFingerprint', () => ({
  videoFingerprint: vi.fn(async () => 'a'.repeat(64)),
  sha256Blob: vi.fn(async () => 'b'.repeat(64)),
}))
vi.mock('../stores/uploadPersistence', () => persistence)

import {
  initializeVideoUploads,
  resetVideoUploads,
  videoUploadState,
} from '../stores/videoUploads'

function session(overrides = {}) {
  return {
    upload_id: 'server-upload',
    filename: 'movie.mp4',
    size: 100,
    name: '成片',
    visibility: 'private',
    fingerprint: 'f'.repeat(64),
    team_id: null,
    chunk_size: 25,
    total_parts: 4,
    status: 'active',
    uploaded_parts: [0],
    expires_at: '2026-08-19T10:00:00Z',
    video: null,
    ...overrides,
  }
}

describe('server video upload discovery', () => {
  beforeEach(() => {
    resetVideoUploads()
    vi.clearAllMocks()
    persistence.listPersistedUploads.mockResolvedValue([])
    api.listVideoUploads.mockResolvedValue({ items: [], total: 0, max_active: 3, part_concurrency: 3 })
  })

  it('discovers and persists a server-only active session as waiting for its file', async () => {
    api.listVideoUploads.mockResolvedValue({
      items: [session()], total: 1, max_active: 5, part_concurrency: 6,
    })

    await initializeVideoUploads(7)

    expect(api.listVideoUploads).toHaveBeenCalledWith({
      token: 'session-token', suppressUnauthorized: true,
    })
    expect(videoUploadState.tasks).toHaveLength(1)
    expect(videoUploadState.tasks[0]).toMatchObject({
      uploadId: 'server-upload', status: 'waiting_file', uploadedParts: [0],
      filename: 'movie.mp4', size: 100, name: '成片', visibility: 'private',
    })
    expect(videoUploadState.maxActiveSessions).toBe(5)
    expect(videoUploadState.maxConcurrentParts).toBe(6)
    expect(persistence.persistUpload).toHaveBeenCalledWith(expect.objectContaining({
      ownerId: 7, uploadId: 'server-upload', filename: 'movie.mp4',
    }))
  })

  it('merges by upload id and replaces stale local metadata with server truth', async () => {
    persistence.listPersistedUploads.mockResolvedValue([{
      key: '7:server-upload', ownerId: 7, uploadId: 'server-upload',
      filename: 'stale.mp4', size: 1, name: '旧名称', visibility: 'public',
      fingerprint: 'old', teamId: 9, chunkSize: 1, totalParts: 1, uploadedParts: [],
    }])
    api.listVideoUploads.mockResolvedValue({
      items: [session({ name: '', team_id: null })], total: 1,
    })

    await initializeVideoUploads(7)

    expect(videoUploadState.tasks).toHaveLength(1)
    expect(videoUploadState.tasks[0]).toMatchObject({
      filename: 'movie.mp4', size: 100, name: '', visibility: 'private',
      fingerprint: 'f'.repeat(64), teamId: null, status: 'waiting_file',
    })
  })

  it('automatically reconciles a server-side finalizing session to completion', async () => {
    api.listVideoUploads.mockResolvedValue({ items: [session({ status: 'finalizing' })], total: 1 })
    const video = { code: 'video-code', media_kind: 'video' }
    api.completeVideoUpload.mockResolvedValue(video)

    await initializeVideoUploads(7)

    expect(api.completeVideoUpload).toHaveBeenCalledWith('server-upload', {
      token: 'session-token', suppressUnauthorized: true,
    })
    expect(videoUploadState.tasks[0]).toMatchObject({ status: 'completed', result: video })
    expect(persistence.removePersistedUpload).toHaveBeenCalledWith('7:server-upload')
  })

  it('ignores an older account discovery response that arrives after a session switch', async () => {
    let resolveOld
    api.listVideoUploads
      .mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
      .mockResolvedValueOnce({ items: [session({ upload_id: 'new-account-upload' })], total: 1 })

    const oldInitialization = initializeVideoUploads(7)
    const newInitialization = initializeVideoUploads(8)
    await newInitialization
    resolveOld({ items: [session({ upload_id: 'old-account-upload' })], total: 1 })
    await oldInitialization

    expect(videoUploadState.tasks.map(task => task.uploadId)).toEqual(['new-account-upload'])
    expect(videoUploadState.tasks[0].ownerId).toBe(8)
  })
})
