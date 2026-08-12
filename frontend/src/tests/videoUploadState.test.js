import { describe, expect, it } from 'vitest'
import { applySession, taskProgress, taskTransferredBytes, uploadStatusLabel } from '../stores/videoUploads'

describe('video upload presentation state', () => {
  it('combines confirmed chunks and in-flight XHR bytes', () => {
    const task = {
      size: 25,
      chunkSize: 10,
      uploadedParts: [0, 2],
      chunkProgress: { 1: 3 },
    }

    expect(taskTransferredBytes(task)).toBe(18)
    expect(taskProgress(task)).toBe(72)
  })

  it('exposes every resumable queue state in Chinese', () => {
    expect(uploadStatusLabel({ status: 'network_paused' })).toBe('网络中断，已暂停')
    expect(uploadStatusLabel({ status: 'manual_paused' })).toBe('已手动暂停')
    expect(uploadStatusLabel({ status: 'waiting_file' })).toBe('等待重新选择文件')
    expect(uploadStatusLabel({ status: 'finalizing' })).toBe('服务端校验中')
  })

  it('moves a restored task back to personal space when the server clears team_id', () => {
    const task = {
      uploadId: 'upload-1',
      chunkSize: 8,
      totalParts: 2,
      uploadedParts: [0],
      expiresAt: 'old',
      teamId: 42,
    }
    applySession(task, {
      upload_id: 'upload-1',
      chunk_size: 8,
      total_parts: 2,
      uploaded_parts: [0],
      expires_at: 'new',
      team_id: null,
    })

    expect(task.teamId).toBeNull()
  })

  it('uses server metadata instead of stale IndexedDB context', () => {
    const task = {
      uploadId: 'upload-1', filename: 'old.mp4', size: 1, name: '旧名称',
      visibility: 'public', fingerprint: 'old', teamId: null,
      chunkSize: 8, totalParts: 2, uploadedParts: [],
    }

    applySession(task, {
      upload_id: 'upload-1', filename: 'server.mp4', size: 99, name: '',
      visibility: 'private', fingerprint: 'server-fingerprint', team_id: 42,
      chunk_size: 16, total_parts: 7, uploaded_parts: [2],
    })

    expect(task).toMatchObject({
      filename: 'server.mp4', size: 99, name: '', visibility: 'private',
      fingerprint: 'server-fingerprint', teamId: 42, chunkSize: 16,
      totalParts: 7, uploadedParts: [2],
    })
  })
})
