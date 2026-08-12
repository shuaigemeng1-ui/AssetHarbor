// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createUser: vi.fn(),
  deleteTeam: vi.fn(),
  deleteUser: vi.fn(),
  getAdminStats: vi.fn(),
  listAdminTeams: vi.fn(),
  listUsers: vi.fn(),
  resetUserPassword: vi.fn(),
  setUserRole: vi.fn(),
}))
const feedback = vi.hoisted(() => ({ confirmAction: vi.fn(), toast: vi.fn() }))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => feedback)

import AdminView from '../components/AdminView.vue'

const admin = { id: 1, username: 'root', role: 'admin', created_at: '2026-08-12T00:00:00Z' }
const member = { id: 2, username: 'alice', role: 'user', created_at: '2026-08-12T00:00:00Z' }

function mountView() {
  return mount(AdminView, { props: { user: admin } })
}

describe('AdminView user lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getAdminStats.mockResolvedValue({
      users: 2, images: 1, videos: 1, media_total: 2, teams: 0,
      storage_bytes: 100, pending_upload_bytes: 0,
    })
    api.listUsers.mockResolvedValue([admin, member])
    api.listAdminTeams.mockResolvedValue([])
    feedback.confirmAction.mockResolvedValue(true)
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('creates a user through the custom modal form', async () => {
    const promptSpy = vi.spyOn(window, 'prompt')
    api.createUser.mockResolvedValue({ id: 3, username: 'editor', role: 'user', created_at: '2026-08-12T01:00:00Z' })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('.section-heading .primary').trigger('click')
    await flushPromises()

    const modal = document.body.querySelector('.base-modal-panel')
    const inputs = modal.querySelectorAll('input')
    inputs[0].value = 'editor'
    inputs[0].dispatchEvent(new Event('input'))
    inputs[1].value = 'secret12'
    inputs[1].dispatchEvent(new Event('input'))
    inputs[2].value = 'secret12'
    inputs[2].dispatchEvent(new Event('input'))
    modal.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()

    expect(api.createUser).toHaveBeenCalledWith('editor', 'secret12', 'user')
    expect(wrapper.text()).toContain('editor')
    expect(promptSpy).not.toHaveBeenCalled()
    expect(document.body.querySelector('.base-modal-panel')).toBeNull()
  })

  it('deletes another user only after confirmation', async () => {
    api.deleteUser.mockResolvedValue(undefined)
    api.listUsers.mockResolvedValueOnce([admin, member]).mockResolvedValueOnce([admin])
    api.getAdminStats
      .mockResolvedValueOnce({ users: 2, images: 1, videos: 1, media_total: 2, teams: 0, storage_bytes: 100, pending_upload_bytes: 0 })
      .mockResolvedValueOnce({ users: 1, images: 0, videos: 0, media_total: 0, teams: 0, storage_bytes: 0, pending_upload_bytes: 0 })
    const wrapper = mountView()
    await flushPromises()
    const row = wrapper.findAll('tbody tr').find(item => item.text().includes('alice'))
    const deleteButton = row.findAll('button').find(button => button.text() === '删除')
    await deleteButton.trigger('click')
    await flushPromises()

    expect(feedback.confirmAction).toHaveBeenCalledWith(expect.objectContaining({
      title: '删除用户',
      danger: true,
    }))
    expect(api.deleteUser).toHaveBeenCalledWith(2)
    expect(wrapper.text()).not.toContain('alice')
  })

  it('resets a password with the custom form instead of a browser prompt', async () => {
    const promptSpy = vi.spyOn(window, 'prompt')
    api.resetUserPassword.mockResolvedValue(undefined)
    const wrapper = mountView()
    await flushPromises()
    const row = wrapper.findAll('tbody tr').find(item => item.text().includes('alice'))
    const resetButton = row.findAll('button').find(button => button.text() === '重置密码')
    await resetButton.trigger('click')
    await flushPromises()

    const modal = document.body.querySelector('.base-modal-panel')
    const inputs = modal.querySelectorAll('input')
    inputs[0].value = 'new-secret'
    inputs[0].dispatchEvent(new Event('input'))
    inputs[1].value = 'new-secret'
    inputs[1].dispatchEvent(new Event('input'))
    modal.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()

    expect(api.resetUserPassword).toHaveBeenCalledWith(2, 'new-secret')
    expect(promptSpy).not.toHaveBeenCalled()
    expect(document.body.querySelector('.base-modal-panel')).toBeNull()
  })
})
