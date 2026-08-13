// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { parseRetryAfter, uploadVideoPart } from '../api'

describe('Retry-After parsing', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('supports seconds and HTTP dates with a bounded delay', () => {
    const now = Date.parse('2026-08-13T10:00:00Z')

    expect(parseRetryAfter('2', now)).toBe(2000)
    expect(parseRetryAfter('Thu, 13 Aug 2026 10:00:10 GMT', now)).toBe(10_000)
    expect(parseRetryAfter('9999', now)).toBe(5 * 60 * 1000)
    expect(parseRetryAfter('invalid', now)).toBeNull()
  })

  it('attaches the server Retry-After delay to a chunk XHR error', async () => {
    let xhr
    class FakeXMLHttpRequest {
      constructor() {
        xhr = this
        this.upload = {}
        this.status = 0
        this.responseText = ''
      }

      open() {}
      send() {}
      abort() { this.onabort?.() }
      setRequestHeader() {}
      getResponseHeader(name) { return name === 'Retry-After' ? '2' : null }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)

    const transport = uploadVideoPart('upload-1', 0, new Blob(['part']), {
      start: 0,
      total: 4,
      sha256: 'a'.repeat(64),
    })
    const rejected = expect(transport.promise).rejects.toMatchObject({
      status: 429,
      retryAfter: '2',
      retryAfterMs: 2000,
    })
    xhr.status = 429
    xhr.responseText = JSON.stringify({ detail: 'too many requests' })
    xhr.onload()

    await rejected
  })
})
