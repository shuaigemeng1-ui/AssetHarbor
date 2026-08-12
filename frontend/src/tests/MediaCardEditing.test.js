// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getSignedLink: vi.fn(),
  getVideoSignedLink: vi.fn(),
  updateImage: vi.fn(),
  updateVideo: vi.fn(),
}))
const feedback = vi.hoisted(() => ({ toast: vi.fn() }))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => feedback)
vi.mock('../utils/clipboard', () => ({ copyText: vi.fn().mockResolvedValue(true) }))

import ImageResult from '../components/ImageResult.vue'
import VideoCard from '../components/VideoCard.vue'

async function submitRename(wrapper, name) {
  const renameButton = wrapper.findAll('button').find(button => button.text() === '重命名')
  await renameButton.trigger('click')
  await flushPromises()
  const modal = document.body.querySelector('.base-modal-panel')
  const input = modal.querySelector('input')
  input.value = name
  input.dispatchEvent(new Event('input'))
  modal.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
}

describe('media card editing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window.HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  })
  afterEach(() => { document.body.innerHTML = '' })

  it('renames an image with the custom modal', async () => {
    const result = {
      code: 'image-code', name: '旧图片名', original_filename: 'old.png', visibility: 'public',
      size: 1, content_type: 'image/png', url: '/i/image-code',
    }
    api.updateImage.mockResolvedValue({ ...result, name: '新图片名' })
    const wrapper = mount(ImageResult, {
      attachTo: document.body,
      props: { item: { status: 'done', result }, editable: true },
    })
    await submitRename(wrapper, '新图片名')
    expect(api.updateImage).toHaveBeenCalledWith('image-code', { name: '新图片名' })
    expect(wrapper.text()).toContain('新图片名')
    expect(document.body.querySelector('.base-modal-panel')).toBeNull()
  })

  it('renames a video with the custom modal', async () => {
    const item = {
      code: 'video-code', name: '旧视频名', original_filename: 'old.mp4', visibility: 'public',
      size: 1, content_type: 'video/mp4', url: '/v/video-code', created_at: '2026-08-12T00:00:00Z',
    }
    api.updateVideo.mockResolvedValue({ ...item, name: '新视频名' })
    const wrapper = mount(VideoCard, {
      attachTo: document.body,
      props: { item, editable: true },
    })
    await flushPromises()
    await submitRename(wrapper, '新视频名')
    expect(api.updateVideo).toHaveBeenCalledWith('video-code', { name: '新视频名' })
    expect(wrapper.text()).toContain('新视频名')
    expect(document.body.querySelector('.base-modal-panel')).toBeNull()
  })

  it('lets the user retry a failed private-image signed link', async () => {
    api.getSignedLink
      .mockRejectedValueOnce(new Error('temporary signing error'))
      .mockResolvedValueOnce({ url: '/i/private?expires=1&sig=ok' })
    const wrapper = mount(ImageResult, {
      props: {
        item: { status: 'done', result: {
          code: 'private-image', name: '私密图片', original_filename: 'private.png',
          visibility: 'private', size: 1, content_type: 'image/png', url: '/i/private-image',
        } },
      },
    })
    await flushPromises()
    const retryButton = wrapper.findAll('button').find(button => button.text() === '重试预览')
    expect(retryButton).toBeTruthy()
    await retryButton.trigger('click')
    await flushPromises()
    expect(api.getSignedLink).toHaveBeenCalledTimes(2)
    expect(wrapper.find('img').attributes('src')).toContain('sig=ok')
  })

  it('lets the user retry a failed private-video signed link', async () => {
    api.getVideoSignedLink
      .mockRejectedValueOnce(new Error('temporary signing error'))
      .mockResolvedValueOnce({ url: '/v/private?expires=1&sig=ok' })
    const wrapper = mount(VideoCard, {
      props: { item: {
        code: 'private-video', name: '私密视频', original_filename: 'private.mp4',
        visibility: 'private', size: 1, content_type: 'video/mp4', url: '/v/private-video',
        created_at: '2026-08-12T00:00:00Z',
      } },
    })
    await flushPromises()
    const retryButton = wrapper.findAll('button').find(button => button.text() === '重试预览')
    expect(retryButton).toBeTruthy()
    await retryButton.trigger('click')
    await flushPromises()
    expect(api.getVideoSignedLink).toHaveBeenCalledTimes(2)
    expect(wrapper.find('video').attributes('src')).toContain('sig=ok')
  })
})
