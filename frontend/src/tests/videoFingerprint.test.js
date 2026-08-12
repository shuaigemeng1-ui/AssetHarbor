import { afterEach, describe, expect, it, vi } from 'vitest'
import { sha256Blob, videoFingerprint } from '../utils/videoFingerprint'

const MiB = 1024 * 1024

describe('videoFingerprint', () => {
  afterEach(() => vi.unstubAllGlobals())
  it('uses the agreed head, middle and tail samples', async () => {
    const bytes = new Uint8Array(3 * MiB + 177)
    for (let index = 0; index < bytes.length; index++) bytes[index] = index % 251
    const file = new Blob([bytes])
    const middle = Math.max(0, Math.floor(file.size / 2) - Math.floor(MiB / 2))
    const tail = Math.max(0, file.size - MiB)
    const samples = await Promise.all([0, middle, tail].map(offset => (
      sha256Blob(file.slice(offset, Math.min(offset + MiB, file.size)))
    )))
    const expected = await sha256Blob(new Blob([`${file.size}:${samples.join(':')}`]))

    await expect(videoFingerprint(file)).resolves.toBe(expected)
  })

  it('hashes overlapping samples for small files independently', async () => {
    const file = new Blob(['small-video-container'])
    const first = await videoFingerprint(file)
    const second = await videoFingerprint(file)

    expect(first).toHaveLength(64)
    expect(second).toBe(first)
  })

  it('falls back to a pure JavaScript SHA-256 implementation on plain HTTP', async () => {
    vi.stubGlobal('crypto', undefined)
    const file = new Blob(['works-without-a-secure-context'])

    await expect(videoFingerprint(file)).resolves.toMatch(/^[a-f0-9]{64}$/)
  })
})
