// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  changePassword: vi.fn(),
  createApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
  listApiKeys: vi.fn(),
  rotateApiKey: vi.fn(),
  setToken: vi.fn(),
}))
const feedback = vi.hoisted(() => ({
  confirmAction: vi.fn(),
  toast: vi.fn(),
}))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => feedback)

import AccountView from '../components/AccountView.vue'

describe('AccountView password revocation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listApiKeys.mockResolvedValue([])
    api.changePassword.mockResolvedValue(undefined)
  })

  it('immediately clears the revoked token and requests app-wide session cleanup', async () => {
    const unauthorized = vi.fn()
    window.addEventListener('oss:unauthorized', unauthorized)
    const wrapper = mount(AccountView, {
      global: { stubs: { AppIcon: { template: '<i />' } } },
    })
    await flushPromises()

    const inputs = wrapper.findAll('.security-form input')
    await inputs[0].setValue('old-password')
    await inputs[1].setValue('new-password')
    await inputs[2].setValue('new-password')
    await wrapper.get('.security-form').trigger('submit')
    await flushPromises()

    expect(api.changePassword).toHaveBeenCalledWith('old-password', 'new-password')
    expect(api.setToken).toHaveBeenCalledWith(null)
    expect(unauthorized).toHaveBeenCalledTimes(1)
    expect(feedback.toast).toHaveBeenCalledWith('密码已安全更新，请使用新密码重新登录', 'success')

    window.removeEventListener('oss:unauthorized', unauthorized)
    wrapper.unmount()
  })
})
