import { sha256 } from 'js-sha256'

const SAMPLE_SIZE = 1024 * 1024

function toHex(buffer) {
  return Array.from(new Uint8Array(buffer), byte => byte.toString(16).padStart(2, '0')).join('')
}

export async function sha256Blob(blob) {
  const data = await blob.arrayBuffer()
  if (globalThis.crypto?.subtle) return toHex(await globalThis.crypto.subtle.digest('SHA-256', data))
  return sha256(new Uint8Array(data))
}

export async function videoFingerprint(file) {
  const middle = Math.max(0, Math.floor(file.size / 2) - Math.floor(SAMPLE_SIZE / 2))
  const tail = Math.max(0, file.size - SAMPLE_SIZE)
  const offsets = [0, middle, tail]
  const hashes = await Promise.all(offsets.map(offset => (
    sha256Blob(file.slice(offset, Math.min(offset + SAMPLE_SIZE, file.size)))
  )))
  const summary = `${file.size}:${hashes.join(':')}`
  const encoded = new TextEncoder().encode(summary)
  if (globalThis.crypto?.subtle) return toHex(await globalThis.crypto.subtle.digest('SHA-256', encoded))
  return sha256(encoded)
}
