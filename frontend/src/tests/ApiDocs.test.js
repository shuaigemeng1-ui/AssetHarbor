// @vitest-environment node
import { readFileSync } from 'node:fs'
import { JSDOM } from 'jsdom'
import { describe, expect, it, vi } from 'vitest'

const html = readFileSync(new URL('../../public/docs.html', import.meta.url), 'utf8')

function loadDocs() {
  const writeText = vi.fn().mockResolvedValue(undefined)
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://media.example.test/docs',
    beforeParse(window) {
      Object.defineProperty(window, 'isSecureContext', { value: true })
      Object.defineProperty(window.navigator, 'clipboard', { value: { writeText } })
    },
  })
  return { dom, writeText }
}

describe('static API documentation', () => {
  it('defaults every copyable example to Python 3 and provides a cURL alternative', () => {
    const { dom } = loadDocs()
    const examples = [...dom.window.document.querySelectorAll('.example')]
    expect(examples.length).toBeGreaterThanOrEqual(9)
    for (const example of examples) {
      expect(example.dataset.defaultLang).toBe('python')
      expect(example.querySelector('[data-code-lang="python"]').getAttribute('aria-selected')).toBe('true')
      expect(example.querySelector('[data-code-panel="python"]').hidden).toBe(false)
      expect(example.querySelector('[data-code-panel="curl"]').hidden).toBe(true)
      expect(example.querySelector('[data-copy]').getAttribute('aria-label')).toContain('Python 3')
    }
  })

  it('switches tabs with the keyboard and copies the active cURL example with feedback', async () => {
    const { dom, writeText } = loadDocs()
    const example = dom.window.document.querySelector('[data-example="upload"] .example')
    const pythonTab = example.querySelector('[data-code-lang="python"]')
    pythonTab.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))
    expect(example.querySelector('[data-code-lang="curl"]').getAttribute('aria-selected')).toBe('true')
    expect(example.querySelector('[data-code-panel="curl"]').hidden).toBe(false)

    example.querySelector('[data-copy]').click()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('curl --fail-with-body'))
    expect(example.querySelector('[data-copy]').textContent).toBe('已复制')
    expect(dom.window.document.getElementById('copy-status').textContent).toContain('已复制')
    dom.window.close()
  })

  it('documents only API-key-callable endpoints and the media access contracts', () => {
    expect(html).toContain('/api/upload')
    expect(html).toContain('/api/video-uploads/{upload_id}/parts/{part_number}')
    expect(html).toContain('/api/video-uploads/{upload_id}/complete')
    expect(html).toContain('/api/media/{code}/link')
    expect(html).toContain('visibility 缺省即 public')
    expect(html).toContain('固定 API 契约')
    expect(html).toContain('JWT-only')
    expect(html).toContain('API Key 绑定用户但仅用于媒体数据面')
    expect(html).toContain('以下无鉴权示例仅适用于公开媒体')
    expect(html).toContain('Authorization: Bearer $OSS_TOKEN')
    expect(html).toContain('仅管理员 JWT 可全局越权')
    expect(html).toContain('管理员 API Key 不继承管理员 JWT 的全局越权能力')
    expect(html).not.toContain('默认私密')
    expect(html).not.toContain('default_visibility')

    // JWT-only control-plane endpoints are out of scope for the API-key guide.
    expect(html).not.toContain('/api/auth/login')
    expect(html).not.toContain('/api/admin/')
    expect(html).not.toContain('/api/keys')

    const { dom } = loadDocs()
    const metadata = dom.window.document.querySelector('[data-example="media-metadata"]')
    expect(metadata).not.toBeNull()
    expect(metadata.querySelector('[data-code-panel="python"]').textContent).toContain('requests.get')
    expect(metadata.querySelector('[data-code-panel="curl"]').textContent).toContain('curl --fail-with-body')
    expect(metadata.textContent).toContain('owner_id')
    expect(metadata.textContent).toContain('original_filename')
    expect(metadata.textContent).toContain('404')
    dom.window.close()
  })

  it('documents request and response parameters for every endpoint', () => {
    const { dom } = loadDocs()
    const document = dom.window.document
    const exampleEndpoints = [...document.querySelectorAll('.endpoint-card[data-example]')]
      .filter(card => card.dataset.example !== 'environment')
    const miniEndpoints = [...document.querySelectorAll('.endpoint-mini')]
    const endpoints = [...exampleEndpoints, ...miniEndpoints]

    expect(endpoints.length).toBeGreaterThanOrEqual(15)
    for (const card of endpoints) {
      expect(card.querySelector('.parameter-wrap'), `${card.dataset.example || card.dataset.endpoint} lacks request params`).not.toBeNull()
      expect(card.querySelector('.response-wrap'), `${card.dataset.example || card.dataset.endpoint} lacks response params`).not.toBeNull()
    }
    expect(html).toContain('请求参数')
    expect(html).toContain('响应参数')
    dom.window.close()
  })

  it('keeps tab and panel relationships unique and avoids decorative emoji', () => {
    const { dom } = loadDocs()
    const ids = [...dom.window.document.querySelectorAll('[id]')].map(element => element.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const tab of dom.window.document.querySelectorAll('[role="tab"]')) {
      expect(dom.window.document.getElementById(tab.getAttribute('aria-controls'))).not.toBeNull()
    }
    expect(html).not.toMatch(/[😀-🙏🌀-🫿]/u)
  })
})
