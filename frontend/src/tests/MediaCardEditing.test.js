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

  it('selects an image by click or Enter and reflects its selected state', async () => {
    const result = {
      code: 'image-code', name: '图片名称', original_filename: 'image.png', visibility: 'public',
      size: 1, content_type: 'image/png', url: '/i/image-code',
    }
    const wrapper = mount(ImageResult, {
      props: { item: { status: 'done', result }, selectable: true, selected: true },
    })
    await flushPromises()

    expect(wrapper.classes()).toContain('selected')
    expect(wrapper.attributes('role')).toBe('button')
    expect(wrapper.attributes('tabindex')).toBe('0')
    expect(wrapper.attributes('aria-pressed')).toBe('true')

    await wrapper.trigger('click')
    await wrapper.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('select')).toEqual([[result], [result]])
  })

  it('keeps retry and remove controls for a failed upload', async () => {
    const wrapper = mount(ImageResult, {
      props: {
        item: {
          status: 'error',
          error: '网络连接中断',
          retryable: true,
          file: { name: 'failed.png', type: '' },
        },
      },
    })

    expect(wrapper.text()).toContain('failed.png')
    expect(wrapper.text()).toContain('网络连接中断')
    expect(wrapper.find('.preview-placeholder .app-icon').exists()).toBe(true)

    const buttons = wrapper.findAll('button')
    await buttons.find(button => button.text() === '重试上传').trigger('click')
    await buttons.find(button => button.text() === '移除').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
    expect(wrapper.emitted('remove-pending')).toHaveLength(1)
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('keeps contextual group actions without adding controls to gallery cards', async () => {
    const result = {
      code: 'grouped-image', name: '分组图片', original_filename: 'grouped.png', visibility: 'public',
      size: 1, content_type: 'image/png', url: '/i/grouped-image',
    }
    const plain = mount(ImageResult, { props: { item: { status: 'done', result } } })
    expect(plain.find('.context-card-actions').exists()).toBe(false)

    const contextual = mount(ImageResult, {
      props: { item: { status: 'done', result }, groupable: true, removable: true },
    })
    const buttons = contextual.findAll('button')
    await buttons.find(button => button.text() === '加入分组').trigger('click')
    await buttons.find(button => button.text() === '移出分组').trigger('click')

    expect(contextual.emitted('add-to-group')).toHaveLength(1)
    expect(contextual.emitted('remove')).toHaveLength(1)
  })

  it('renames an image from a contextual card', async () => {
    const item = {
      code: 'image-code', name: '旧图片名', original_filename: 'old.png', visibility: 'public',
      size: 1, content_type: 'image/png', url: '/i/image-code',
    }
    api.updateImage.mockResolvedValue({ ...item, name: '新图片名' })
    const wrapper = mount(ImageResult, {
      attachTo: document.body,
      props: { item: { status: 'done', result: item }, editable: true },
    })
    await flushPromises()
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
