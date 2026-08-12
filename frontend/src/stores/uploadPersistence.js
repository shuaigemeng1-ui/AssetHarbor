const DB_NAME = 'oss-video-uploads'
const STORE_NAME = 'sessions'
const DB_VERSION = 1

function openDatabase() {
  return new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) {
      reject(new Error('当前浏览器不支持 IndexedDB'))
      return
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onerror = () => reject(request.error)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        const store = request.result.createObjectStore(STORE_NAME, { keyPath: 'key' })
        store.createIndex('ownerId', 'ownerId', { unique: false })
      }
    }
    request.onsuccess = () => resolve(request.result)
  })
}

async function transact(mode, callback) {
  const db = await openDatabase()
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, mode)
      const request = callback(transaction.objectStore(STORE_NAME))
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
      transaction.onerror = () => reject(transaction.error)
    })
  } finally {
    db.close()
  }
}

export async function listPersistedUploads(ownerId) {
  try {
    return await transact('readonly', store => store.index('ownerId').getAll(ownerId))
  } catch {
    return []
  }
}

export async function persistUpload(record) {
  try {
    await transact('readwrite', store => store.put(record))
  } catch {
    // Uploading still works when private browsing disables IndexedDB.
  }
}

export async function removePersistedUpload(key) {
  try {
    await transact('readwrite', store => store.delete(key))
  } catch {
    // Best-effort local cleanup.
  }
}
