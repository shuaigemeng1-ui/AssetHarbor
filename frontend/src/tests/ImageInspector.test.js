// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  addMediaGroupItems: vi.fn(),
  createMediaGroup: vi.fn(),
  getSignedLink: vi.fn(),
  listMediaGroups: vi.fn(),
  updateImage: vi.fn(),
}))
const feedback = vi.hoisted(() => ({ toast: vi.fn() }))
const clipboard = vi.hoisted(() => ({ copyText: vi.fn() }))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => feedback)
vi.mock('../utils/clipboard', () => clipboard)

import ImageInspector from '../components/ImageInspector.vue'

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
  id: 21,
  code: 'hero-code',
  name: '首页主视觉',
  original_filename: 'hero-final.png',
  size: 1536,
  content_type: 'image/png',
  visibility: 'public',
  url: '/i/hero-code',
  owner_id: 7,
  owner_username: 'alice',
  team_id: 9,
}

function mountInspector(overrides = {}) {
  const item = overrides.item || { ...baseItem }
  return mount(ImageInspector, {
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

describe('ImageInspector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clipboard.copyText.mockResolvedValue(true)
  })

  it('renders the real image fields, preview, owner, and team scope', () => {
    const wrapper = mountInspector({ isGlobalAdmin: true })

    expect(wrapper.attributes('aria-label')).toBe('图片详情')
    expect(wrapper.text()).toContain('首页主视觉')
    expect(wrapper.text()).toContain('hero-final.png')
    expect(wrapper.text()).toContain('1.5 KB')
    expect(wrapper.text()).toContain('image/png')
    expect(wrapper.text()).toContain('hero-code')
    expect(wrapper.text()).toContain('公开访问')
    expect(wrapper.text()).toContain('alice')
    expect(wrapper.text()).toContain('团队空间 #9')
    expect(wrapper.get('.inspector-preview img').attributes('src')).toBe('/i/hero-code')
  })

  it('loads and copies a fresh signed link for a private image', async () => {
    api.getSignedLink
      .mockResolvedValueOnce({ url: '/i/private?sig=preview' })
      .mockResolvedValueOnce({ url: '/i/private?sig=fresh' })
    const wrapper = mountInspector({
      item: { ...baseItem, visibility: 'private', url: '/i/hero-code' },
    })
    await flushPromises()

    expect(wrapper.get('.inspector-preview img').attributes('src')).toContain('sig=preview')
    const copyButton = wrapper.findAll('button').find(button => button.text() === '复制链接')
    await copyButton.trigger('click')
    await flushPromises()

    expect(api.getSignedLink).toHaveBeenCalledTimes(2)
    expect(clipboard.copyText).toHaveBeenCalledWith('/i/private?sig=fresh')
    expect(feedback.toast).toHaveBeenCalledWith('限时签名链接已复制', 'success')
  })

  it('allows a failed public preview to be retried', async () => {
    const wrapper = mountInspector()

    await wrapper.get('.inspector-preview img').trigger('error')
    expect(wrapper.text()).toContain('重试预览')
    await wrapper.get('.preview-empty button').trigger('click')

    expect(wrapper.get('.inspector-preview img').attributes('src')).toBe('/i/hero-code')
  })

  it('emits parent-owned visibility and delete actions with the selected image', async () => {
    const item = { ...baseItem }
    const wrapper = mountInspector({ item, canManage: true })

    const visibilityButton = wrapper.findAll('button').find(button => button.text() === '设为私密')
    const deleteButton = wrapper.findAll('button').find(button => button.text() === '删除图片')
    await visibilityButton.trigger('click')
    await deleteButton.trigger('click')

    expect(wrapper.emitted('toggle-visibility')).toEqual([[item]])
    expect(wrapper.emitted('delete')).toEqual([[item]])
  })

  it('renames through the API, updates the visible name, and emits the response', async () => {
    const updated = { ...baseItem, name: '新版主视觉' }
    api.updateImage.mockResolvedValue(updated)
    const wrapper = mountInspector()

    const renameButton = wrapper.findAll('button').find(button => button.text() === '重命名')
    await renameButton.trigger('click')
    await wrapper.get('#inspector-rename-image-input').setValue('新版主视觉')
    await wrapper.get('#inspector-rename-image-form').trigger('submit')
    await flushPromises()

    expect(api.updateImage).toHaveBeenCalledWith('hero-code', { name: '新版主视觉' })
    expect(wrapper.text()).toContain('新版主视觉')
    expect(wrapper.emitted('updated')).toEqual([[updated]])
    expect(feedback.toast).toHaveBeenCalledWith('图片名称已更新', 'success')
  })

  it('opens the existing collection picker with the current scope and permissions', async () => {
    const wrapper = mountInspector({ canManage: true, canManageGroups: true })

    const groupButton = wrapper.findAll('button').find(button => button.text() === '加入分组')
    await groupButton.trigger('click')
    const picker = wrapper.getComponent(CollectionPickerModalStub)

    expect(picker.props('media')).toEqual(expect.objectContaining({ code: 'hero-code', name: '首页主视觉' }))
    expect(picker.props('teamId')).toBe(9)
    expect(picker.props('userId')).toBe(7)
    expect(picker.props('canManage')).toBe(true)
  })
})
