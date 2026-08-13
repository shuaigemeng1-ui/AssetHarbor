// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  changePassword: vi.fn(),
  createApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
  getToken: vi.fn(),
  listApiKeys: vi.fn(),
  rotateApiKey: vi.fn(),
  setToken: vi.fn(),
}))
const feedback = vi.hoisted(() => ({
  confirmAction: vi.fn(),
  toast: vi.fn(),
}))
const clipboard = vi.hoisted(() => ({ copyText: vi.fn() }))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => feedback)
vi.mock('../utils/clipboard', () => clipboard)

import AccountView from '../components/AccountView.vue'

const sampleKey = {
  id: 3,
  name: '备份脚本',
  key: 'complete-secret-value',
  key_prefix: 'K3yAbc12',
  created_at: '2026-08-10T10:20:00Z',
  last_used_at: '2026-08-12T10:20:00Z',
}

function mountAccountView() {
  return mount(AccountView, {
    attachTo: document.body,
    global: {
      stubs: {
        AppIcon: {
          props: ['name'],
          template: '<i :data-icon="name" />',
        },
      },
    },
  })
}

function keyDialog() {
  return document.body.querySelector('.base-modal-panel')
}

function buttonWithText(wrapper, text) {
  return wrapper.findAll('button').find(button => button.text().trim() === text)
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((onResolve, onReject) => {
    resolve = onResolve
    reject = onReject
  })
  return { promise, resolve, reject }
}

describe('AccountView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listApiKeys.mockResolvedValue([])
    api.changePassword.mockResolvedValue(undefined)
    api.getToken.mockReturnValue('active-token')
    clipboard.copyText.mockResolvedValue(true)
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('renders the reference two-column information architecture with real key metadata', async () => {
    api.listApiKeys.mockResolvedValue([sampleKey])
    const wrapper = mountAccountView()
    await flushPromises()

    expect(api.listApiKeys).toHaveBeenCalledTimes(1)
    expect(wrapper.get('.account-primary-column').find('.api-panel').exists()).toBe(true)
    expect(wrapper.get('.account-primary-column').find('.api-help').exists()).toBe(true)
    expect(wrapper.get('.account-layout > .password-panel').exists()).toBe(true)
    expect(wrapper.findAll('.key-table thead th').map(cell => cell.text())).toEqual([
      '密钥名称',
      'API Key',
      '创建时间',
      '最近使用',
      '操作',
    ])
    expect(wrapper.get('.key-name').text()).toBe('备份脚本')
    expect(wrapper.get('.masked-key code').text()).toBe('K3yAbc12••••••••')
    expect(wrapper.text()).not.toContain('complete-secret-value')
    expect(wrapper.get('.api-help a').attributes('href')).toBe('/docs')

    wrapper.unmount()
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

  it('keeps failed password changes signed in and exposes accessible visibility controls', async () => {
    api.changePassword.mockRejectedValue(new Error('当前密码不正确'))
    const wrapper = mountAccountView()
    await flushPromises()

    const inputs = wrapper.findAll('.security-form input')
    expect(inputs.map(input => input.attributes('type'))).toEqual(['password', 'password', 'password'])
    await wrapper.get('button[aria-label="显示当前密码"]').trigger('click')
    expect(inputs[0].attributes('type')).toBe('text')
    expect(wrapper.get('button[aria-label="隐藏当前密码"]').attributes('aria-pressed')).toBe('true')

    await inputs[0].setValue('wrong-password')
    await inputs[1].setValue('new-password')
    await inputs[2].setValue('new-password')
    await wrapper.get('.security-form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('.security-form [role="alert"]').text()).toBe('当前密码不正确')
    expect(api.setToken).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  it('signs out when password credentials were invalidated concurrently', async () => {
    const error = Object.assign(new Error('账户凭据已发生变化，请重新登录'), { status: 409 })
    api.changePassword.mockRejectedValue(error)
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

    expect(api.setToken).toHaveBeenCalledWith(null)
    expect(unauthorized).toHaveBeenCalledTimes(1)
    expect(feedback.toast).toHaveBeenCalledWith('账户凭据已发生变化，请重新登录', 'error')

    window.removeEventListener('oss:unauthorized', unauthorized)
    wrapper.unmount()
  })

  it('does not let an old password response clear a newly authenticated session', async () => {
    const pending = deferred()
    api.changePassword.mockReturnValue(pending.promise)
    api.getToken.mockReturnValue('old-token')
    const unauthorized = vi.fn()
    window.addEventListener('oss:unauthorized', unauthorized)
    const wrapper = mountAccountView()
    await flushPromises()

    const inputs = wrapper.findAll('.security-form input')
    await inputs[0].setValue('old-password')
    await inputs[1].setValue('new-password')
    await inputs[2].setValue('new-password')
    await wrapper.get('.security-form').trigger('submit')
    await wrapper.vm.$nextTick()

    api.getToken.mockReturnValue('new-account-token')
    pending.resolve()
    await flushPromises()

    expect(api.setToken).not.toHaveBeenCalled()
    expect(unauthorized).not.toHaveBeenCalled()
    expect(feedback.toast).not.toHaveBeenCalledWith(
      '密码已安全更新，请使用新密码重新登录',
      'success',
    )

    window.removeEventListener('oss:unauthorized', unauthorized)
    wrapper.unmount()
  })

  it('asks for a name only after the user clicks generate key', async () => {
    const wrapper = mountAccountView()
    await flushPromises()

    expect(document.body.querySelector('[aria-label="API Key 名称"]')).toBeNull()
    expect(api.createApiKey).not.toHaveBeenCalled()

    await wrapper.get('.generate-key-button').trigger('click')
    await flushPromises()

    expect(keyDialog()).not.toBeNull()
    expect(keyDialog().querySelector('[aria-label="API Key 名称"]')).toBe(document.activeElement)
    expect(api.createApiKey).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  it('does not misreport an API Key load failure as an empty list', async () => {
    api.listApiKeys.mockRejectedValue(new Error('API Key 加载失败'))
    const wrapper = mountAccountView()
    await flushPromises()

    expect(wrapper.get('.api-panel [role="alert"]').text()).toBe('API Key 加载失败')
    expect(wrapper.text()).not.toContain('还没有 API Key')

    await wrapper.get('.generate-key-button').trigger('click')
    await flushPromises()
    const cancel = [...keyDialog().querySelectorAll('button')]
      .find(button => button.textContent.trim() === '取消')
    cancel.click()
    await flushPromises()

    expect(wrapper.get('.api-panel [role="alert"]').text()).toBe('API Key 加载失败')
    expect(wrapper.text()).not.toContain('还没有 API Key')

    wrapper.unmount()
  })

  it('shows a loading state and blocks creation until the initial key list is known', async () => {
    const pending = deferred()
    api.listApiKeys.mockReturnValue(pending.promise)
    const wrapper = mountAccountView()
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.key-empty[role="status"]').text()).toBe('正在加载 API Key…')
    expect(wrapper.get('.generate-key-button').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain('还没有 API Key')

    pending.resolve([])
    await flushPromises()
    expect(wrapper.get('.generate-key-button').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('还没有 API Key')

    wrapper.unmount()
  })

  it('creates a key with the trimmed dialog name and then reveals it once', async () => {
    api.createApiKey.mockResolvedValue({
      ...sampleKey,
      id: 7,
      key: 'complete-secret-shown-once',
    })
    const wrapper = mountAccountView()
    await flushPromises()
    await wrapper.get('.generate-key-button').trigger('click')
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
    expect(wrapper.get('.key-value').text()).toBe('complete-secret-shown-once')
    expect(wrapper.get('.key-reveal button.copy').element).toBe(document.activeElement)

    wrapper.unmount()
  })

  it('closes the name dialog without creating a key when cancelled', async () => {
    const wrapper = mountAccountView()
    await flushPromises()
    await wrapper.get('.generate-key-button').trigger('click')
    await flushPromises()

    const cancel = [...keyDialog().querySelectorAll('button')]
      .find(button => button.textContent.trim() === '取消')
    cancel.click()
    await flushPromises()

    expect(keyDialog()).toBeNull()
    expect(api.createApiKey).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  it('switches between the two supported API Key authentication examples', async () => {
    const wrapper = mountAccountView()
    await flushPromises()

    expect(wrapper.get('.api-code-example').text()).toContain('Authorization: Bearer <YOUR_API_KEY>')
    expect(wrapper.get('.api-code-example').text()).not.toContain('X-API-Key:')
    await wrapper.get('#header-tab').trigger('click')
    expect(wrapper.get('.api-code-example').text()).toContain('X-API-Key: <YOUR_API_KEY>')
    expect(wrapper.get('#header-tab').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('#bearer-tab').attributes('aria-pressed')).toBe('false')

    wrapper.unmount()
  })

  it('copies only the one-time revealed complete key and resets the copied state', async () => {
    api.createApiKey.mockResolvedValue({
      ...sampleKey,
      id: 7,
      key: 'complete-secret-shown-once',
    })
    const wrapper = mountAccountView()
    await flushPromises()
    await wrapper.get('.generate-key-button').trigger('click')
    await flushPromises()

    const input = keyDialog().querySelector('[aria-label="API Key 名称"]')
    input.value = '备份脚本'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    keyDialog().querySelector('form').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }))
    await flushPromises()

    vi.useFakeTimers()
    await wrapper.get('.key-reveal button.copy').trigger('click')
    await flushPromises()
    expect(clipboard.copyText).toHaveBeenCalledWith('complete-secret-shown-once')
    expect(feedback.toast).toHaveBeenCalledWith('完整 API Key 已复制', 'success')
    expect(wrapper.get('.key-reveal button.copy').text()).toBe('已复制')

    vi.advanceTimersByTime(1500)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.key-reveal button.copy').text()).toBe('复制')

    wrapper.unmount()
  })

  it('confirms rotation and revocation before mutating a key', async () => {
    const rotatedKey = { ...sampleKey, id: 8 }
    const deleteRefresh = deferred()
    api.listApiKeys
      .mockResolvedValueOnce([sampleKey])
      .mockResolvedValueOnce([rotatedKey])
      .mockReturnValueOnce(deleteRefresh.promise)
    feedback.confirmAction.mockResolvedValue(true)
    api.rotateApiKey.mockResolvedValue({
      ...rotatedKey,
      key: 'rotated-secret-shown-once',
    })
    api.deleteApiKey.mockResolvedValue(undefined)
    const wrapper = mountAccountView()
    await flushPromises()

    await buttonWithText(wrapper, '重新生成').trigger('click')
    await flushPromises()
    expect(feedback.confirmAction).toHaveBeenCalledWith(expect.objectContaining({
      title: '重新生成 API Key',
      danger: true,
    }))
    expect(api.rotateApiKey).toHaveBeenCalledWith(3)
    expect(wrapper.get('.key-value').text()).toBe('rotated-secret-shown-once')
    expect(wrapper.get('.key-reveal button.copy').element).toBe(document.activeElement)
    expect(wrapper.get('.key-table tbody th[scope="row"]').text()).toBe('备份脚本')

    await buttonWithText(wrapper, '撤销').trigger('click')
    await flushPromises()
    expect(feedback.confirmAction).toHaveBeenLastCalledWith(expect.objectContaining({
      title: '撤销 API Key',
      danger: true,
    }))
    expect(api.deleteApiKey).toHaveBeenCalledWith(8)
    expect(api.listApiKeys).toHaveBeenCalledTimes(3)
    expect(wrapper.find('.key-reveal').exists()).toBe(false)
    expect(wrapper.get('#api-key-heading').element).toBe(document.activeElement)

    deleteRefresh.resolve([])
    await flushPromises()

    wrapper.unmount()
  })

  it('disables every credential mutation while a password change is pending', async () => {
    api.listApiKeys.mockResolvedValue([sampleKey])
    const pending = deferred()
    api.changePassword.mockReturnValue(pending.promise)
    const wrapper = mountAccountView()
    await flushPromises()

    const inputs = wrapper.findAll('.security-form input')
    await inputs[0].setValue('old-password')
    await inputs[1].setValue('new-password')
    await inputs[2].setValue('new-password')
    await wrapper.get('.security-form').trigger('submit')
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.generate-key-button').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label^="重新生成 API Key"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label^="撤销 API Key"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.password-submit').attributes('disabled')).toBeDefined()

    pending.resolve()
    await flushPromises()
    wrapper.unmount()
  })

  it('keeps optimistic key metadata when the post-create refresh fails', async () => {
    const firstLoad = deferred()
    const secondLoad = deferred()
    api.listApiKeys
      .mockReturnValueOnce(firstLoad.promise)
      .mockReturnValueOnce(secondLoad.promise)
    api.createApiKey.mockResolvedValue({
      ...sampleKey,
      id: 7,
      key: 'complete-secret-shown-once',
    })
    const wrapper = mountAccountView()

    // The create button is intentionally disabled during the initial load, so
    // resolve the first request and then overlap a later refresh with creation.
    firstLoad.resolve([])
    await flushPromises()
    await wrapper.get('.generate-key-button').trigger('click')
    await flushPromises()
    const input = keyDialog().querySelector('[aria-label="API Key 名称"]')
    input.value = '备份脚本'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    keyDialog().querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()

    expect(wrapper.get('.key-name').text()).toBe('备份脚本')
    expect(wrapper.get('.masked-key code').text()).toBe('K3yAbc12••••••••')
    expect(wrapper.get('.key-value').text()).toBe('complete-secret-shown-once')
    expect(keyDialog()).toBeNull()
    expect(wrapper.get('.key-reveal button.copy').attributes('disabled')).toBeUndefined()
    expect(wrapper.emitted('credential-busy').at(-1)).toEqual([false])

    secondLoad.reject(new Error('刷新失败'))
    await flushPromises()
    expect(wrapper.get('.key-name').text()).toBe('备份脚本')
    expect(wrapper.get('.api-panel [role="alert"]').text()).toBe('刷新失败')

    wrapper.unmount()
  })

  it('preserves an existing one-time secret when a later rotation fails', async () => {
    const revealedKey = {
      ...sampleKey,
      id: 7,
      key: 'secret-that-still-needs-saving',
    }
    api.listApiKeys
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ ...sampleKey, id: 7 }])
    api.createApiKey.mockResolvedValue(revealedKey)
    feedback.confirmAction.mockResolvedValue(true)
    api.rotateApiKey.mockRejectedValue(new Error('轮换失败'))
    const wrapper = mountAccountView()
    await flushPromises()

    await wrapper.get('.generate-key-button').trigger('click')
    await flushPromises()
    const input = keyDialog().querySelector('[aria-label="API Key 名称"]')
    input.value = '备份脚本'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    keyDialog().querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(wrapper.get('.key-value').text()).toBe('secret-that-still-needs-saving')

    await buttonWithText(wrapper, '重新生成').trigger('click')
    await flushPromises()
    expect(wrapper.get('.key-value').text()).toBe('secret-that-still-needs-saving')
    expect(wrapper.get('.api-panel [role="alert"]').text()).toBe('轮换失败')

    wrapper.unmount()
  })

  it('disables password submission while a key rotation is pending', async () => {
    api.listApiKeys.mockResolvedValue([sampleKey])
    feedback.confirmAction.mockResolvedValue(true)
    const pending = deferred()
    api.rotateApiKey.mockReturnValue(pending.promise)
    const wrapper = mountAccountView()
    await flushPromises()

    const inputs = wrapper.findAll('.security-form input')
    await inputs[0].setValue('old-password')
    await inputs[1].setValue('new-password')
    await inputs[2].setValue('new-password')
    expect(wrapper.get('.password-submit').attributes('disabled')).toBeUndefined()

    await buttonWithText(wrapper, '重新生成').trigger('click')
    await flushPromises()
    expect(wrapper.get('.password-submit').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-key-action="rotate"]').text()).toBe('…')
    expect(wrapper.get('[data-key-action="rotate"]').attributes('aria-label')).toContain('正在重新生成 API Key')
    expect(wrapper.get('[data-key-action="delete"]').text()).toBe('撤销')
    await wrapper.get('.security-form').trigger('submit')
    expect(api.changePassword).not.toHaveBeenCalled()

    pending.resolve({
      ...sampleKey,
      id: 8,
      key: 'rotated-secret-shown-once',
    })
    await flushPromises()
    wrapper.unmount()
  })

  it('keeps row actions compact while key revocation is pending', async () => {
    api.listApiKeys
      .mockResolvedValueOnce([sampleKey])
      .mockResolvedValueOnce([])
    feedback.confirmAction.mockResolvedValue(true)
    const pending = deferred()
    api.deleteApiKey.mockReturnValue(pending.promise)
    const wrapper = mountAccountView()
    await flushPromises()

    await buttonWithText(wrapper, '撤销').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-key-action="rotate"]').text()).toBe('重新生成')
    expect(wrapper.get('[data-key-action="delete"]').text()).toBe('…')
    expect(wrapper.get('[data-key-action="delete"]').attributes('aria-label')).toContain('正在撤销 API Key')

    pending.resolve()
    await flushPromises()
    wrapper.unmount()
  })

  it('keeps key mutations idle when their confirmation is cancelled', async () => {
    api.listApiKeys.mockResolvedValue([sampleKey])
    feedback.confirmAction.mockResolvedValue(false)
    const wrapper = mountAccountView()
    await flushPromises()

    await buttonWithText(wrapper, '重新生成').trigger('click')
    await flushPromises()
    await buttonWithText(wrapper, '撤销').trigger('click')
    await flushPromises()

    expect(feedback.confirmAction).toHaveBeenCalledTimes(2)
    expect(api.rotateApiKey).not.toHaveBeenCalled()
    expect(api.deleteApiKey).not.toHaveBeenCalled()
    expect(buttonWithText(wrapper, '重新生成').attributes('disabled')).toBeUndefined()
    expect(buttonWithText(wrapper, '撤销').element).toBe(document.activeElement)

    wrapper.unmount()
  })
})
