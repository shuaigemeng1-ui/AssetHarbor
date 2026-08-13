// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createUser: vi.fn(),
  deleteTeam: vi.fn(),
  deleteUser: vi.fn(),
  getAdminStats: vi.fn(),
  getAdminTrafficStats: vi.fn(),
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
const team = { id: 7, name: 'design', description: '', owner_username: 'root', member_count: 2 }

function trafficReport(overrides = {}) {
  return {
    days: 7,
    start_date: '2026-08-06',
    end_date: '2026-08-12',
    summary: { request_count: 12, error_count: 1, request_bytes: 1024, response_bytes: 2048, total_bytes: 3072 },
    anonymous: { request_count: 2, error_count: 0, request_bytes: 0, response_bytes: 128, total_bytes: 128 },
    telemetry_complete: true,
    telemetry_dropped_events: 0,
    daily: [
      { date: '2026-08-11', request_count: 4, error_count: 0, request_bytes: 256, response_bytes: 512, total_bytes: 768 },
      { date: '2026-08-12', request_count: 8, error_count: 1, request_bytes: 768, response_bytes: 1536, total_bytes: 2304 },
    ],
    routes: [{ route: '/api/media', method: 'GET', request_count: 5, error_count: 0, request_bytes: 0, response_bytes: 1000, total_bytes: 1000 }],
    api_keys: [{ api_key_id: 9, key_name: '同步任务', key_prefix: 'oss_live_ab', user_id: 2, username: 'alice', request_count: 3, error_count: 0, request_bytes: 10, response_bytes: 20, total_bytes: 30 }],
    members: [{
      user_id: 2, username: 'alice', role: 'user', storage_bytes: 6000,
      image_bytes: 1000, video_bytes: 5000, pending_upload_bytes: 2000, total_usage_bytes: 8000,
      request_count: 10, error_count: 1, request_bytes: 900, response_bytes: 1900, total_bytes: 2800,
    }],
    ...overrides,
  }
}

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
    api.getAdminTrafficStats.mockResolvedValue(trafficReport())
    feedback.confirmAction.mockResolvedValue(true)
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('creates a user through the custom modal form', async () => {
    const promptSpy = vi.spyOn(window, 'prompt')
    const editor = { id: 3, username: 'editor', role: 'user', created_at: '2026-08-12T01:00:00Z' }
    api.createUser.mockResolvedValue(editor)
    api.getAdminTrafficStats
      .mockResolvedValueOnce(trafficReport())
      .mockResolvedValueOnce(trafficReport({
        members: [...trafficReport().members, {
          user_id: 3, username: 'editor', role: 'user', storage_bytes: 0,
          image_bytes: 0, video_bytes: 0, pending_upload_bytes: 0, total_usage_bytes: 0,
          request_count: 0, error_count: 0, request_bytes: 0, response_bytes: 0, total_bytes: 0,
        }],
      }))
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
    expect(api.getAdminTrafficStats).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.member-usage-table').text()).toContain('editor')
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
    api.getAdminTrafficStats
      .mockResolvedValueOnce(trafficReport())
      .mockResolvedValueOnce(trafficReport({ members: [], api_keys: [] }))
    const wrapper = mountView()
    await flushPromises()
    const row = wrapper.findAll('.admin-table tbody tr').find(item => item.text().includes('alice'))
    const deleteButton = row.findAll('button').find(button => button.text() === '删除')
    await deleteButton.trigger('click')
    await flushPromises()

    expect(feedback.confirmAction).toHaveBeenCalledWith(expect.objectContaining({
      title: '删除用户',
      danger: true,
    }))
    expect(api.deleteUser).toHaveBeenCalledWith(2)
    expect(api.getAdminTrafficStats).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('.admin-table tbody tr').some(item => item.text().includes('alice'))).toBe(false)
    expect(wrapper.get('.member-usage-table').text()).not.toContain('alice')
  })

  it('refreshes dashboard and storage attribution after disbanding a team', async () => {
    api.deleteTeam.mockResolvedValue(undefined)
    api.listAdminTeams.mockResolvedValueOnce([team]).mockResolvedValueOnce([])
    const wrapper = mountView()
    await flushPromises()

    const teamRow = wrapper.findAll('.admin-table tbody tr').find(item => item.text().includes('design'))
    await teamRow.get('button').trigger('click')
    await flushPromises()

    expect(api.deleteTeam).toHaveBeenCalledWith(7)
    expect(api.getAdminTrafficStats).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('.admin-table tbody tr').some(item => item.text().includes('design'))).toBe(false)
  })

  it('resets a password with the custom form instead of a browser prompt', async () => {
    const promptSpy = vi.spyOn(window, 'prompt')
    api.resetUserPassword.mockResolvedValue(undefined)
    const wrapper = mountView()
    await flushPromises()
    const row = wrapper.findAll('.admin-table tbody tr').find(item => item.text().includes('alice'))
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

  it('renders traffic, member storage and reloads a selected time range', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(api.getAdminTrafficStats).toHaveBeenCalledWith(7)
    expect(wrapper.text()).toContain('API 调用与流量')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('同步任务')
    expect(wrapper.text()).toContain('alice')
    expect(wrapper.find('progress').attributes('aria-label')).toContain('调用 4 次')

    await wrapper.get('.traffic-range select').setValue('30')
    await flushPromises()
    expect(api.getAdminTrafficStats).toHaveBeenLastCalledWith(30)
  })

  it('warns when the current process dropped telemetry events', async () => {
    api.getAdminTrafficStats.mockResolvedValue(trafficReport({
      telemetry_complete: false,
      telemetry_dropped_events: 7,
    }))
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('.traffic-warning').text()).toContain('7')
    expect(wrapper.get('.traffic-warning').text()).toContain('数据可能偏低')
  })
})
