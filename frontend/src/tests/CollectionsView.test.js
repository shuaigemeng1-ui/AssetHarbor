// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createMediaGroup: vi.fn(),
  deleteMediaGroup: vi.fn(),
  listMediaGroupItems: vi.fn(),
  listMediaGroups: vi.fn(),
  removeMediaGroupItem: vi.fn(),
  updateMediaGroup: vi.fn(),
}))
const feedback = vi.hoisted(() => ({ confirmAction: vi.fn(), toast: vi.fn() }))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => feedback)

import CollectionsView from '../components/CollectionsView.vue'

const group = {
  id: 4,
  name: '产品素材',
  description: '发布会相关素材',
  color: '#2563eb',
  sort_order: 0,
  owner_id: 7,
  owner_username: 'alice',
  team_id: null,
  item_count: 1,
  created_at: '2026-08-12T00:00:00Z',
  updated_at: '2026-08-12T00:00:00Z',
}

function mountView(props = {}) {
  return mount(CollectionsView, {
    props: { user: { id: 7, role: 'user' }, ...props },
    global: {
      stubs: {
        ImageResult: {
          props: ['item', 'removable'],
          emits: ['remove'],
          template: '<button class="remove-media" :data-code="item.result.code" @click="$emit(\'remove\')">{{ item.result.name }} · 移出</button>',
        },
        VideoCard: true,
        VideoPlayerModal: true,
      },
    },
  })
}

describe('CollectionsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listMediaGroups.mockResolvedValue({ items: [{ ...group }], total: 1 })
    api.listMediaGroupItems.mockResolvedValue({
      items: [{
        code: 'img-code',
        name: '主视觉',
        original_filename: 'hero.png',
        media_kind: 'image',
        owner_id: 7,
      }],
      total: 1,
    })
    feedback.confirmAction.mockResolvedValue(true)
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('loads a group and removes media without deleting the original asset', async () => {
    api.removeMediaGroupItem.mockResolvedValue(undefined)
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('产品素材')
    expect(wrapper.text()).toContain('主视觉')
    await wrapper.get('.remove-media').trigger('click')
    await flushPromises()

    expect(feedback.confirmAction).toHaveBeenCalledWith(expect.objectContaining({ title: '移出分组' }))
    expect(api.removeMediaGroupItem).toHaveBeenCalledWith(4, 'img-code')
    expect(wrapper.find('.remove-media').exists()).toBe(false)
    expect(wrapper.text()).toContain('这个分组还是空的')
  })

  it('creates a personal group with the selected color and description', async () => {
    api.createMediaGroup.mockResolvedValue({
      ...group,
      id: 9,
      name: '客户案例',
      description: '案例视频与截图',
      color: '#16835a',
      item_count: 0,
    })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('.section-heading .primary').trigger('click')
    await flushPromises()
    const modal = document.body.querySelector('.base-modal-panel')
    const inputs = modal.querySelectorAll('input')
    const textarea = modal.querySelector('textarea')
    await wrapper.vm.$nextTick()
    inputs[0].value = '客户案例'
    inputs[0].dispatchEvent(new Event('input'))
    textarea.value = '案例视频与截图'
    textarea.dispatchEvent(new Event('input'))
    inputs[1].value = '#16835a'
    inputs[1].dispatchEvent(new Event('input'))
    modal.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()

    expect(api.createMediaGroup).toHaveBeenCalledWith(expect.objectContaining({
      name: '客户案例',
      description: '案例视频与截图',
      color: '#16835a',
      teamId: null,
    }))
    expect(wrapper.text()).toContain('客户案例')
  })

  it('keeps only the group action bar when embedded in a team', async () => {
    const wrapper = mountView({ teamId: 3, canManage: true, embedded: true })
    await flushPromises()

    expect(wrapper.classes()).toContain('collections-view-embedded')
    expect(wrapper.find('.section-heading h2').exists()).toBe(false)
    expect(wrapper.get('.section-heading .primary').text()).toBe('新建分组')
  })

  it('renders one embedded toolbar with the kind filter and no nested detail toolbar', async () => {
    const wrapper = mountView({ teamId: 3, canManage: true, embedded: true })
    await flushPromises()

    // The kind tabs and item search live in the single top toolbar, matching
    // the image/video tabs, instead of a second toolbar inside the detail.
    const heading = wrapper.get('.section-heading')
    expect(heading.find('.kind-tabs').exists()).toBe(true)
    expect(heading.find('.item-search').exists()).toBe(true)
    expect(wrapper.findAll('.kind-tabs')).toHaveLength(1)
    expect(wrapper.find('.collection-toolbar').exists()).toBe(false)

    // Kind filtering still works from the embedded toolbar.
    await heading.get('.kind-tabs button:nth-child(3)').trigger('click')
    await flushPromises()
    expect(api.listMediaGroupItems).toHaveBeenLastCalledWith(4, expect.objectContaining({ kind: 'video' }))
  })
})
