// @vitest-environment jsdom
import 'fake-indexeddb/auto'
import { beforeEach, describe, expect, it } from 'vitest'
import { listPersistedUploads, persistUpload, removePersistedUpload } from '../stores/uploadPersistence'

function deleteDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase('oss-video-uploads')
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
    request.onblocked = () => resolve()
  })
}

describe('video upload IndexedDB metadata', () => {
  beforeEach(deleteDatabase)

  it('restores only metadata belonging to the signed-in owner', async () => {
    const record = {
      key: '7:upload-1',
      ownerId: 7,
      uploadId: 'upload-1',
      filename: 'movie.mp4',
      size: 99,
      fingerprint: 'abc',
      uploadedParts: [0, 2],
    }
    await persistUpload(record)
    await persistUpload({ ...record, key: '8:upload-2', ownerId: 8, uploadId: 'upload-2' })

    await expect(listPersistedUploads(7)).resolves.toEqual([record])
  })

  it('removes a completed or cancelled session without storing file contents', async () => {
    const record = {
      key: '7:upload-3',
      ownerId: 7,
      uploadId: 'upload-3',
      filename: 'clip.webm',
      size: 42,
      fingerprint: 'def',
      uploadedParts: [],
    }
    await persistUpload(record)
    await removePersistedUpload(record.key)

    await expect(listPersistedUploads(7)).resolves.toEqual([])
  })
})
