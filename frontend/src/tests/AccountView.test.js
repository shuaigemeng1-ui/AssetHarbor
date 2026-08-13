// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

function mountAccountView() {
  return mount(AccountView, {
    global: { stubs: { AppIcon: { template: '<i />' } } },
  })
}

function keyDialog() {
  return document.body.querySelector('.base-modal-panel')
}

describe('AccountView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listApiKeys.mockResolvedValue([])
    api.changePassword.mockResolvedValue(undefined)
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('immediately clears the revoked token and requests app-wide session cleanup', async () => {
    const unauthorized = vi.fn()
    window.addEventListener('oss:unauthorized', unauthorized)
    const wrapper = mountAccountView()
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

  it('asks for a name only after the user clicks generate key', async () => {
    const wrapper = mountAccountView()
    await flushPromises()

    expect(document.body.querySelector('[aria-label="API Key 名称"]')).toBeNull()
    expect(api.createApiKey).not.toHaveBeenCalled()

    await wrapper.get('.key-create-actions button').trigger('click')
    await flushPromises()

    expect(keyDialog()).not.toBeNull()
    expect(keyDialog().querySelector('[aria-label="API Key 名称"]')).toBe(document.activeElement)
    expect(api.createApiKey).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  it('creates a key with the trimmed dialog name and then reveals it', async () => {
    api.createApiKey.mockResolvedValue({
      id: 7,
      name: '备份脚本',
      key: 'oss_live_secret',
      key_prefix: 'oss_live',
      created_at: '2026-08-13T00:00:00Z',
      last_used_at: null,
    })
    const wrapper = mountAccountView()
    await flushPromises()
    await wrapper.get('.key-create-actions button').trigger('click')
    await flushPromises()

    const input = keyDialog().querySelector('[aria-label="API Key 名称"]')
    input.value = '  备份脚本  '
    input.dispatchEvent(new Event('input', { bubbles: true }))
    keyDialog().querySelector('form').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }))
    await flushPromises()

    expect(api.createApiKey).toHaveBeenCalledTimes(1)
    expect(api.createApiKey).toHaveBeenCalledWith('备份脚本')
    expect(api.listApiKeys).toHaveBeenCalledTimes(2)
    expect(keyDialog()).toBeNull()
    expect(wrapper.get('.key-value').text()).toBe('oss_live_secret')

    wrapper.unmount()
  })

  it('closes the name dialog without creating a key when cancelled', async () => {
    const wrapper = mountAccountView()
    await flushPromises()
    await wrapper.get('.key-create-actions button').trigger('click')
    await flushPromises()

    const cancel = [...keyDialog().querySelectorAll('button')]
      .find(button => button.textContent.trim() === '取消')
    cancel.click()
    await flushPromises()

    expect(keyDialog()).toBeNull()
    expect(api.createApiKey).not.toHaveBeenCalled()

    wrapper.unmount()
  })
})
