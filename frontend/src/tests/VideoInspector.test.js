// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  addMediaGroupItems: vi.fn(),
  createMediaGroup: vi.fn(),
  getVideoSignedLink: vi.fn(),
  listMediaGroups: vi.fn(),
  updateVideo: vi.fn(),
}))
const feedback = vi.hoisted(() => ({ toast: vi.fn() }))
const clipboard = vi.hoisted(() => ({ copyText: vi.fn() }))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => feedback)
vi.mock('../utils/clipboard', () => clipboard)

import VideoInspector from '../components/VideoInspector.vue'

const BaseModalStub = {
  name: 'BaseModal',
  template: '<div data-test="rename-modal"><slot /><slot name="footer" /></div>',
}

const CollectionPickerModalStub = {
  name: 'CollectionPickerModal',
  props: ['media', 'teamId', 'userId', 'canManage'],
  emits: ['close', 'added'],
  template: '<div data-test="collection-picker" />',
}

const baseItem = {
  id: 31,
  code: 'intro-code',
  name: '产品介绍',
  original_filename: 'intro-final.mp4',
  size: 10 * 1024 * 1024,
  content_type: 'video/mp4',
  visibility: 'public',
  url: '/v/intro-code',
  owner_id: 7,
  owner_username: 'alice',
  team_id: 9,
  created_at: '2026-08-12T00:00:00Z',
}

function mountInspector(overrides = {}) {
  const item = overrides.item || { ...baseItem }
  return mount(VideoInspector, {
    props: {
      item,
      user: { id: 7, username: 'alice', role: 'user' },
      teamId: 9,
      groupable: true,
      ...overrides,
      item,
    },
    global: {
      stubs: {
        AppIcon: { template: '<i class="icon-stub" />' },
        BaseModal: BaseModalStub,
        CollectionPickerModal: CollectionPickerModalStub,
      },
    },
  })
}

describe('VideoInspector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clipboard.copyText.mockResolvedValue(true)
  })

  it('renders the image-inspector layout, contained preview, and real video fields', () => {
    const wrapper = mountInspector({ isGlobalAdmin: true })

    expect(wrapper.classes()).toEqual(expect.arrayContaining(['image-inspector', 'video-inspector']))
    expect(wrapper.attributes('aria-label')).toBe('视频详情')
    expect(wrapper.text()).toContain('产品介绍')
    expect(wrapper.text()).toContain('intro-final.mp4')
    expect(wrapper.text()).toContain('10.0 MB')
    expect(wrapper.text()).toContain('video/mp4')
    expect(wrapper.text()).toContain('intro-code')
    expect(wrapper.text()).toContain('公开访问')
    expect(wrapper.text()).toContain('创建时间')
    expect(wrapper.text()).toContain('alice')
    expect(wrapper.text()).toContain('团队空间 #9')
    expect(wrapper.get('.inspector-preview video').attributes('src')).toBe('/v/intro-code')
    expect(wrapper.get('.inspector-preview video').element).toBeInstanceOf(HTMLVideoElement)
  })

  it('emits play from the fixed preview card', async () => {
    const item = { ...baseItem }
    const wrapper = mountInspector({ item })

    await wrapper.get('.preview-play-button').trigger('click')

    expect(wrapper.emitted('play')).toEqual([[item]])
  })

  it('loads and copies a fresh signed link for a private video', async () => {
    api.getVideoSignedLink
      .mockResolvedValueOnce({ url: '/v/private?sig=preview' })
      .mockResolvedValueOnce({ url: '/v/private?sig=fresh' })
    const wrapper = mountInspector({
      item: { ...baseItem, visibility: 'private', url: '/v/intro-code' },
    })
    await flushPromises()

    expect(wrapper.get('.inspector-preview video').attributes('src')).toContain('sig=preview')
    const copyButton = wrapper.findAll('button').find(button => button.text() === '复制链接')
    await copyButton.trigger('click')
    await flushPromises()

    expect(api.getVideoSignedLink).toHaveBeenCalledTimes(2)
    expect(clipboard.copyText).toHaveBeenCalledWith('/v/private?sig=fresh')
    expect(feedback.toast).toHaveBeenCalledWith('限时签名链接已复制', 'success')
  })

  it('allows a failed public preview to be retried', async () => {
    const wrapper = mountInspector()

    await wrapper.get('.inspector-preview video').trigger('error')
    expect(wrapper.text()).toContain('重试预览')
    expect(wrapper.get('.preview-download').attributes('href')).toBe('/v/intro-code?download=1')
    await wrapper.get('.preview-empty button').trigger('click')

    expect(wrapper.get('.inspector-preview video').attributes('src')).toBe('/v/intro-code')
  })

  it('emits parent-owned visibility and delete actions with the selected video', async () => {
    const item = { ...baseItem }
    const wrapper = mountInspector({ item, canManage: true })

    const visibilityButton = wrapper.findAll('button').find(button => button.text() === '设为私密')
    const deleteButton = wrapper.findAll('button').find(button => button.text() === '删除视频')
    await visibilityButton.trigger('click')
    await deleteButton.trigger('click')

    expect(wrapper.emitted('toggle-visibility')).toEqual([[item]])
    expect(wrapper.emitted('delete')).toEqual([[item]])
  })

  it('renames through the video API, updates the visible name, and emits the response', async () => {
    const updated = { ...baseItem, name: '新版产品介绍' }
    api.updateVideo.mockResolvedValue(updated)
    const wrapper = mountInspector()

    const renameButton = wrapper.findAll('button').find(button => button.text() === '重命名')
    await renameButton.trigger('click')
    await wrapper.get('#inspector-rename-video-input').setValue('新版产品介绍')
    await wrapper.get('#inspector-rename-video-form').trigger('submit')
    await flushPromises()

    expect(api.updateVideo).toHaveBeenCalledWith('intro-code', { name: '新版产品介绍' })
    expect(wrapper.text()).toContain('新版产品介绍')
    expect(wrapper.emitted('updated')).toEqual([[updated]])
    expect(feedback.toast).toHaveBeenCalledWith('视频名称已更新', 'success')
  })

  it('opens the existing collection picker with the current scope and permissions', async () => {
    const wrapper = mountInspector({ canManage: true, canManageGroups: true })

    const groupButton = wrapper.findAll('button').find(button => button.text() === '加入分组')
    await groupButton.trigger('click')
    const picker = wrapper.getComponent(CollectionPickerModalStub)

    expect(picker.props('media')).toEqual(expect.objectContaining({ code: 'intro-code', name: '产品介绍' }))
    expect(picker.props('teamId')).toBe(9)
    expect(picker.props('userId')).toBe(7)
    expect(picker.props('canManage')).toBe(true)
  })

  it('exposes a focusable inspector element', () => {
    const wrapper = mount(VideoInspector, {
      attachTo: document.body,
      props: {
        item: { ...baseItem },
        user: { id: 7, username: 'alice', role: 'user' },
        teamId: 9,
      },
      global: {
        stubs: {
          AppIcon: { template: '<i class="icon-stub" />' },
          BaseModal: BaseModalStub,
          CollectionPickerModal: CollectionPickerModalStub,
        },
      },
    })

    expect(wrapper.vm.getElement()).toBe(wrapper.element)
    wrapper.vm.focus()
    expect(document.activeElement).toBe(wrapper.element)
    wrapper.unmount()
  })
})
