// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchPublicConfig: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  setToken: vi.fn(),
}))

vi.mock('../api', () => api)

import AuthView from '../components/AuthView.vue'

function mountAuth() {
  return mount(AuthView, {
    global: {
      stubs: { AppIcon: { template: '<i />' } },
    },
  })
}

describe('AuthView registration policy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.login.mockResolvedValue({
      access_token: 'token',
      user: { id: 1, username: 'tester', role: 'user' },
    })
    api.register.mockResolvedValue({ id: 1, username: 'tester', role: 'user' })
  })

  it('fails closed and hides registration when the server disables it', async () => {
    api.fetchPublicConfig.mockResolvedValue({ registration_mode: 'closed' })
    const wrapper = mountAuth()
    await flushPromises()

    expect(wrapper.findAll('.auth-tabs button').map(button => button.text())).toEqual(['登录'])
    expect(wrapper.text()).not.toContain('创建账户')
  })

  it('collects and submits the invite code in invite mode', async () => {
    api.fetchPublicConfig.mockResolvedValue({ registration_mode: 'invite' })
    const wrapper = mountAuth()
    await flushPromises()

    await wrapper.findAll('.auth-tabs button')[1].trigger('click')
    const inputs = wrapper.findAll('input')
    await inputs.find(input => input.attributes('autocomplete') === 'username').setValue('tester')
    await inputs.find(input => input.attributes('autocomplete') === 'new-password').setValue('pass123')
    await inputs.find(input => input.attributes('autocomplete') === 'one-time-code').setValue('invite-42')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(api.register).toHaveBeenCalledWith('tester', 'pass123', 'invite-42')
    expect(api.setToken).toHaveBeenCalledWith('token')
  })
})
