// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  addMediaGroupItems: vi.fn(),
  createMediaGroup: vi.fn(),
  listMediaGroups: vi.fn(),
}))
const feedback = vi.hoisted(() => ({ toast: vi.fn() }))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => feedback)

import CollectionPickerModal from '../components/CollectionPickerModal.vue'

describe('CollectionPickerModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listMediaGroups.mockResolvedValue({
      items: [
        { id: 1, name: '我的分组', owner_id: 7, color: '#2563eb', item_count: 2 },
        { id: 2, name: '其他人的分组', owner_id: 8, color: '#d92d20', item_count: 4 },
      ],
      total: 2,
    })
    api.addMediaGroupItems.mockResolvedValue({ added: 1, skipped: 0, group: { id: 1, name: '我的分组' } })
  })

  afterEach(() => { document.body.innerHTML = '' })

  it('only offers manageable team groups and adds the media code', async () => {
    const wrapper = mount(CollectionPickerModal, {
      attachTo: document.body,
      props: {
        media: { code: 'video-code', name: '发布会视频' },
        teamId: 5,
        userId: 7,
        canManage: false,
      },
    })
    await flushPromises()

    expect(document.body.textContent).toContain('我的分组')
    expect(document.body.textContent).not.toContain('其他人的分组')
    const addButton = [...document.body.querySelectorAll('button')].find(button => button.textContent.includes('加入所选分组'))
    addButton.click()
    await flushPromises()

    expect(api.listMediaGroups).toHaveBeenCalledWith({ teamId: 5, q: '', limit: 50, offset: 0 })
    expect(api.addMediaGroupItems).toHaveBeenCalledWith(1, ['video-code'])
    expect(wrapper.emitted('added')).toHaveLength(1)
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('creates and adds in one atomic request', async () => {
    api.listMediaGroups.mockResolvedValueOnce({ items: [], total: 0 })
    api.createMediaGroup.mockResolvedValue({
      id: 9, name: '新分组', owner_id: 7, team_id: null, color: '#2563eb', item_count: 1,
    })
    const wrapper = mount(CollectionPickerModal, {
      attachTo: document.body,
      props: { media: { code: 'image-code', name: '封面' }, userId: 7 },
    })
    await flushPromises()
    const createButton = [...document.body.querySelectorAll('button')].find(button => button.textContent.includes('新建分组'))
    createButton.click()
    await flushPromises()
    const modal = document.body.querySelector('.base-modal-panel')
    const nameInput = modal.querySelector('.quick-create input:not([type="color"])')
    nameInput.value = '新分组'
    nameInput.dispatchEvent(new Event('input'))
    modal.querySelector('.quick-create').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()

    expect(api.createMediaGroup).toHaveBeenCalledWith(expect.objectContaining({
      name: '新分组',
      teamId: null,
      codes: ['image-code'],
    }))
    expect(api.addMediaGroupItems).not.toHaveBeenCalled()
  })

  it('continues paging when the first team page has no manageable groups', async () => {
    api.listMediaGroups
      .mockResolvedValueOnce({ items: [{ id: 2, name: '别人分组', owner_id: 8 }], total: 2 })
      .mockResolvedValueOnce({ items: [{ id: 3, name: '我的后续分组', owner_id: 7, item_count: 0 }], total: 2 })
    mount(CollectionPickerModal, {
      attachTo: document.body,
      props: { media: { code: 'image-code', name: '封面' }, teamId: 5, userId: 7 },
    })
    await flushPromises()
    expect(document.body.textContent).toContain('这一页没有可管理的分组')
    const continueButton = [...document.body.querySelectorAll('button')].find(button => button.textContent.includes('继续查找'))
    continueButton.click()
    await flushPromises()

    expect(api.listMediaGroups).toHaveBeenLastCalledWith({ teamId: 5, q: '', limit: 50, offset: 1 })
    expect(document.body.textContent).toContain('我的后续分组')
  })
})
