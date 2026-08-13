// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ getVideoSignedLink: vi.fn() }))

vi.mock('../api', () => api)

import VideoPlayerModal from '../components/VideoPlayerModal.vue'

const publicVideo = {
  code: 'portrait-video',
  name: '竖屏视频',
  original_filename: 'portrait.mp4',
  size: 1024,
  content_type: 'video/mp4',
  visibility: 'public',
  url: '/v/portrait-video',
}

describe('VideoPlayerModal', () => {
  beforeEach(() => {
    vi.spyOn(window.HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
    vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
    document.body.classList.remove('modal-open')
  })

  it('contains portrait and landscape videos inside the fixed player card', async () => {
    const wrapper = mount(VideoPlayerModal, {
      attachTo: document.body,
      props: { item: publicVideo },
    })
    await flushPromises()

    const stage = document.body.querySelector('.player-stage')
    const video = document.body.querySelector('.player-media')
    const playerSource = readFileSync(resolve(process.cwd(), 'src/components/VideoPlayerModal.vue'), 'utf8')
    const modalSource = readFileSync(resolve(process.cwd(), 'src/components/BaseModal.vue'), 'utf8')

    expect(stage).not.toBeNull()
    expect(video.getAttribute('src')).toBe('/v/portrait-video')
    expect(video.hasAttribute('controls')).toBe(true)
    expect(video.hasAttribute('playsinline')).toBe(true)
    expect(document.body.querySelector('.base-modal-panel').classList).toContain('viewport-fit')
    expect(document.body.querySelector('.base-modal-panel').classList).toContain('wide')
    expect(playerSource).toMatch(/\.player-stage\s*\{[^}]*position:\s*relative;[^}]*overflow:\s*hidden;/s)
    expect(playerSource).toMatch(/\.player-stage \.player-media\s*\{[^}]*position:\s*absolute;[^}]*max-height:\s*100%;[^}]*object-fit:\s*contain;/s)
    expect(modalSource).toMatch(/\.base-modal-panel\.viewport-fit \.base-modal-content\s*\{[^}]*overflow:\s*hidden;/s)

    wrapper.unmount()
  })
})
