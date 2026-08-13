// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { request, uploadVideoPart } from '../api'

describe('request() network timeouts', () => {
  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('rejects with a retryable status-0 timeout error when a request hangs', async () => {
    vi.useFakeTimers()
    let requestSignal
    vi.stubGlobal('fetch', vi.fn((_url, options) => new Promise((_resolve, reject) => {
      requestSignal = options.signal
      options.signal.addEventListener('abort', () => reject(options.signal.reason))
    })))

    const pending = request('/api/slow-endpoint', { timeout: 100 })
    // Attach the assertion before the timer fires so the rejection is handled
    // synchronously, then let the timeout elapse.
    const rejected = expect(pending).rejects.toMatchObject({ status: 0, name: 'TimeoutError' })
    expect(requestSignal).toBeDefined()
    await vi.advanceTimersByTimeAsync(100)

    // status 0 + TimeoutError is what the upload store treats as a network
    // failure (network_paused), so a hung connection cannot stall the queue.
    await rejected
  })

  it('aborts hung requests with the default 30s timeout when none is supplied', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn((_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(options.signal.reason))
    })))

    const pending = request('/api/slow-endpoint')
    await vi.advanceTimersByTimeAsync(29_999)
    let settled = false
    pending.then(() => { settled = true }, () => { settled = true })
    await vi.advanceTimersByTimeAsync(0)
    expect(settled).toBe(false)

    const rejected = expect(pending).rejects.toMatchObject({ status: 0, name: 'TimeoutError' })
    await vi.advanceTimersByTimeAsync(1)
    await rejected
  })

  it('does not convert a caller-supplied abort into a timeout error', async () => {
    const controller = new AbortController()
    let receivedSignal
    vi.stubGlobal('fetch', vi.fn((_url, options) => new Promise((_resolve, reject) => {
      receivedSignal = options.signal
      options.signal.addEventListener('abort', () => reject(options.signal.reason))
    })))

    const pending = request('/api/slow-endpoint', { signal: controller.signal })
    expect(receivedSignal).toBe(controller.signal)
    controller.abort()

    // Pause/cancel aborts must surface as their own AbortError, never as the
    // timeout error, so the store's abort handling keeps working.
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('keeps resolving successful requests after a short timeout elapses', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn(async () => ({
      status: 200,
      ok: true,
      json: vi.fn(async () => ({ ok: true })),
    })))

    const pending = request('/api/quick', { timeout: 100 })
    await vi.advanceTimersByTimeAsync(10_000)
    await expect(pending).resolves.toEqual({ ok: true })
  })
})

describe('uploadVideoPart() timeout', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('rejects with a status-0 network-style error when the chunk XHR times out', async () => {
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
      getResponseHeader() { return null }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)

    const transport = uploadVideoPart('upload-1', 0, new Blob(['part']), {
      start: 0,
      total: 4,
      sha256: 'a'.repeat(64),
    })
    const rejected = expect(transport.promise).rejects.toMatchObject({ status: 0, name: 'TimeoutError' })

    expect(xhr.timeout).toBe(60_000)
    xhr.ontimeout()

    await rejected
  })

  it('keeps abort() rejections distinct from timeouts', async () => {
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
      getResponseHeader() { return null }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)

    const transport = uploadVideoPart('upload-1', 0, new Blob(['part']), {
      start: 0,
      total: 4,
      sha256: 'a'.repeat(64),
    })
    const rejected = expect(transport.promise).rejects.toMatchObject({ aborted: true })
    xhr.abort()

    await rejected
  })
})
