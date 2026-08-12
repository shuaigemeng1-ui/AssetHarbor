// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchMe: vi.fn(async () => ({ id: 1, username: 'tester', role: 'user' })),
  getToken: vi.fn(() => 'token'),
  setToken: vi.fn(),
}))

vi.mock('../api', async importOriginal => ({
  ...await importOriginal(),
  ...api,
}))
vi.mock('../stores/videoUploads', () => ({
  activeVideoUploadCount: 0,
  initializeVideoUploads: vi.fn(),
  resetVideoUploads: vi.fn(),
}))

import App from '../App.vue'

describe('global upload center navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.location.hash = '#/overview'
    window.scrollTo = vi.fn()
  })

  it('keeps the upload center reachable even with no active uploads', async () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          AppIcon: { template: '<i />' },
          HomeView: true,
          GalleryView: true,
          VideoView: true,
          CollectionsView: true,
          TeamsView: true,
          AdminView: true,
          AccountView: true,
          AuthView: true,
          UiFeedback: true,
          VideoUploadQueue: { template: '<div class="queue-stub" />' },
          BaseModal: { template: '<div class="modal-stub"><slot /></div>' },
        },
      },
    })
    await flushPromises()

    const button = wrapper.get('.nav-upload-center')
    expect(button.attributes('aria-label')).toBe('打开全局上传中心')
    await button.trigger('click')
    expect(wrapper.find('.modal-stub').exists()).toBe(true)
    expect(wrapper.find('.queue-stub').exists()).toBe(true)
  })
})
