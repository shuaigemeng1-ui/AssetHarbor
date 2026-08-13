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
    api.fetchMe.mockResolvedValue({ id: 1, username: 'tester', role: 'user' })
    api.getToken.mockReturnValue('token')
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
    expect(wrapper.get('.rail-upload-center').attributes('aria-label')).toBe('打开视频上传中心')
    wrapper.unmount()
  })

  it.each(['images', 'videos'])('renders #/%s with the full-width library shell', async route => {
    window.location.hash = `#/${route}`
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
          VideoUploadQueue: true,
          BaseModal: true,
        },
      },
    })
    await flushPromises()
    expect(wrapper.get('.workspace-main').classes()).toContain('workspace-main-library')
    wrapper.unmount()
  })

  it('shows administrator global media navigation and a separate personal image route', async () => {
    api.fetchMe.mockResolvedValue({ id: 99, username: 'admin', role: 'admin' })
    window.location.hash = '#/images'
    const wrapper = mount(App, {
      global: {
        stubs: {
          AppIcon: { template: '<i />' },
          HomeView: true,
          GalleryView: {
            props: ['scope'],
            template: '<div class="gallery-scope-stub" :data-scope="scope" />',
          },
          VideoView: true,
          CollectionsView: true,
          TeamsView: true,
          AdminView: true,
          AccountView: true,
          AuthView: true,
          UiFeedback: true,
          VideoUploadQueue: true,
          BaseModal: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('全站媒体库')
    expect(wrapper.text()).toContain('全站图片')
    expect(wrapper.text()).toContain('全站视频')
    expect(wrapper.get('.context-title').text()).toBe('全站媒体库')
    expect(wrapper.get('.gallery-scope-stub').attributes('data-scope')).toBe('all')

    const myImages = wrapper.findAll('.side-nav button').find(button => button.text().includes('我的图片'))
    await myImages.trigger('click')

    expect(window.location.hash).toBe('#/my-images')
    expect(wrapper.get('.context-title').text()).toBe('个人空间')
    expect(wrapper.get('.gallery-scope-stub').attributes('data-scope')).toBe('mine')
    wrapper.unmount()
  })

  it('does not expose the administrator-only personal alias to regular users', async () => {
    window.location.hash = '#/my-images'
    const wrapper = mount(App, {
      global: {
        stubs: {
          AppIcon: { template: '<i />' },
          HomeView: true,
          GalleryView: {
            props: ['scope'],
            template: '<div class="gallery-scope-stub" :data-scope="scope" />',
          },
          VideoView: true,
          CollectionsView: true,
          TeamsView: true,
          AdminView: true,
          AccountView: true,
          AuthView: true,
          UiFeedback: true,
          VideoUploadQueue: true,
          BaseModal: true,
        },
      },
    })
    await flushPromises()

    expect(window.location.hash).toBe('#/images')
    expect(wrapper.get('.gallery-scope-stub').attributes('data-scope')).toBe('mine')
    expect(wrapper.text()).not.toContain('全站媒体库')
    wrapper.unmount()
  })

  it('preserves the administrator personal-image bookmark until login resolves the role', async () => {
    api.getToken.mockReturnValue(null)
    window.location.hash = '#/my-images'
    const wrapper = mount(App, {
      global: {
        stubs: {
          AppIcon: { template: '<i />' },
          HomeView: true,
          GalleryView: {
            props: ['scope'],
            template: '<div class="gallery-scope-stub" :data-scope="scope" />',
          },
          VideoView: true,
          CollectionsView: true,
          TeamsView: true,
          AdminView: true,
          AccountView: true,
          AuthView: {
            template: '<button class="auth-stub" @click="$emit(\'authed\', { id: 99, username: \'admin\', role: \'admin\' })">login</button>',
          },
          UiFeedback: true,
          VideoUploadQueue: true,
          BaseModal: true,
        },
      },
    })
    await flushPromises()

    expect(window.location.hash).toBe('#/my-images')
    await wrapper.get('.auth-stub').trigger('click')
    await flushPromises()

    expect(window.location.hash).toBe('#/my-images')
    expect(wrapper.get('.gallery-scope-stub').attributes('data-scope')).toBe('mine')
    wrapper.unmount()
  })
})
