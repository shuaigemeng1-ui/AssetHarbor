// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getToken, request, setToken, uploadVideoPart } from '../api'

function unauthorizedResponse() {
  return {
    status: 401,
    ok: false,
    json: vi.fn(async () => ({ detail: 'unauthorized' })),
  }
}

describe('stale unauthorized responses', () => {
  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('does not let an old fetch response clear a newly authenticated account', async () => {
    let finishRequest
    vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finishRequest = resolve })))
    const unauthorized = vi.fn()
    window.addEventListener('oss:unauthorized', unauthorized)

    setToken('old-account-token')
    const pending = request('/api/images')
    setToken('new-account-token')
    finishRequest(unauthorizedResponse())

    await expect(pending).rejects.toThrow('登录已过期')
    expect(getToken()).toBe('new-account-token')
    expect(unauthorized).not.toHaveBeenCalled()
    window.removeEventListener('oss:unauthorized', unauthorized)
  })

  it('still clears the token when the 401 belongs to the current fetch session', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => unauthorizedResponse()))
    const unauthorized = vi.fn()
    window.addEventListener('oss:unauthorized', unauthorized)

    setToken('current-token')
    await expect(request('/api/images')).rejects.toThrow('登录已过期')

    expect(getToken()).toBeNull()
    expect(unauthorized).toHaveBeenCalledTimes(1)
    window.removeEventListener('oss:unauthorized', unauthorized)
  })

  it('does not let an old chunk XHR clear a newly authenticated account', async () => {
    let xhr
    class FakeXMLHttpRequest {
      constructor() {
        xhr = this
        this.upload = {}
        this.headers = {}
        this.status = 0
        this.responseText = ''
      }

      open() {}
      send() {}
      abort() { this.onabort?.() }
      setRequestHeader(name, value) { this.headers[name] = value }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)
    const unauthorized = vi.fn()
    window.addEventListener('oss:unauthorized', unauthorized)

    setToken('old-account-token')
    const transport = uploadVideoPart('upload-1', 0, new Blob(['part']), {
      start: 0,
      total: 4,
      sha256: 'a'.repeat(64),
    })
    const rejected = expect(transport.promise).rejects.toMatchObject({ status: 401 })
    setToken('new-account-token')
    xhr.status = 401
    xhr.responseText = JSON.stringify({ detail: 'unauthorized' })
    xhr.onload()

    await rejected
    expect(xhr.headers.Authorization).toBe('Bearer old-account-token')
    expect(getToken()).toBe('new-account-token')
    expect(unauthorized).not.toHaveBeenCalled()
    window.removeEventListener('oss:unauthorized', unauthorized)
  })
})
