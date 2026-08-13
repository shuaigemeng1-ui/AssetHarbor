// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchMe: vi.fn(async () => ({ id: 1, username: 'tester', role: 'user' })),
  getToken: vi.fn(() => 'token'),
  setToken: vi.fn(),
}))
const videoUploads = vi.hoisted(() => ({
  activeVideoUploadCount: 0,
  initializeVideoUploads: vi.fn(),
  resetVideoUploads: vi.fn(),
}))

vi.mock('../api', async importOriginal => ({
  ...await importOriginal(),
  ...api,
}))
vi.mock('../stores/videoUploads', () => videoUploads)

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
          VideoUploadQueue: {
            props: { allScopes: Boolean },
            template: '<div class="queue-stub" :data-all-scopes="String(allScopes)" />',
          },
          BaseModal: { template: '<div class="modal-stub"><slot /></div>' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('.global-rail').exists()).toBe(false)
    expect(wrapper.findAll('.context-sidebar')).toHaveLength(1)
    expect(wrapper.get('.sidebar-user > .sidebar-user-logout').attributes('aria-label')).toBe('退出登录')
    expect(wrapper.find('.side-nav > .nav-logout:not(.nav-logout-mobile)').exists()).toBe(false)
    expect(wrapper.find('.nav-logout-mobile').exists()).toBe(true)
    expect(wrapper.findAll('.nav-upload-center')).toHaveLength(1)
    const button = wrapper.get('.context-sidebar .nav-upload-center')
    expect(button.attributes('aria-label')).toBe('打开视频上传中心')
    await button.trigger('click')
    expect(wrapper.find('.modal-stub').exists()).toBe(true)
    expect(wrapper.find('.queue-stub').exists()).toBe(true)
    expect(wrapper.get('.queue-stub').attributes('data-all-scopes')).toBe('true')
    wrapper.unmount()
  })

  it.each([
    ['desktop account card', '.sidebar-user-logout'],
    ['mobile navigation', '.nav-logout-mobile'],
  ])('logs out from the %s entry', async (_label, selector) => {
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
          AuthView: { template: '<div class="auth-stub" />' },
          UiFeedback: true,
          VideoUploadQueue: true,
          BaseModal: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get(selector).trigger('click')
    await flushPromises()

    expect(api.setToken).toHaveBeenCalledWith(null)
    expect(videoUploads.resetVideoUploads).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.workspace-shell').exists()).toBe(false)
    expect(wrapper.find('.auth-stub').exists()).toBe(true)
    wrapper.unmount()
  })

  it.each(['images', 'my-images', 'videos', 'my-videos'])('renders #/%s with the full-width library shell', async route => {
    if (route.startsWith('my-')) {
      api.fetchMe.mockResolvedValue({ id: 99, username: 'admin', role: 'admin' })
    }
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

  it('shows administrator global media navigation and separate personal media routes', async () => {
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
          VideoView: {
            props: ['scope'],
            template: '<div class="video-scope-stub" :data-scope="scope" />',
          },
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
    expect(wrapper.find('.global-rail').exists()).toBe(false)
    expect(wrapper.findAll('.nav-upload-center')).toHaveLength(1)
    expect(wrapper.text()).toContain('媒体概览')
    expect(wrapper.text()).toContain('管理中心')
    expect(wrapper.text()).toContain('账户与密钥')
    expect(wrapper.text()).toContain('退出登录')
    expect(wrapper.findAll('[aria-current="page"]')).toHaveLength(1)

    const myImages = wrapper.findAll('.side-nav button').find(button => button.text().includes('我的图片'))
    await myImages.trigger('click')

    expect(window.location.hash).toBe('#/my-images')
    expect(wrapper.get('.context-title').text()).toBe('个人空间')
    expect(wrapper.get('.gallery-scope-stub').attributes('data-scope')).toBe('mine')

    const myVideos = wrapper.findAll('.side-nav button').find(button => button.text().includes('我的视频'))
    await myVideos.trigger('click')

    expect(window.location.hash).toBe('#/my-videos')
    expect(wrapper.get('.context-title').text()).toBe('个人空间')
    expect(wrapper.get('.video-scope-stub').attributes('data-scope')).toBe('mine')

    const globalVideos = wrapper.findAll('.side-nav button').find(button => button.text().includes('全站视频'))
    await globalVideos.trigger('click')

    expect(window.location.hash).toBe('#/videos')
    expect(wrapper.get('.context-title').text()).toBe('全站媒体库')
    expect(wrapper.get('.video-scope-stub').attributes('data-scope')).toBe('all')
    expect(wrapper.findAll('[aria-current="page"]')).toHaveLength(1)
    wrapper.unmount()
  })

  it.each([
    ['account', { id: 1, username: 'tester', role: 'user' }],
    ['admin', { id: 99, username: 'admin', role: 'admin' }],
  ])('keeps the merged navigation reachable from #/%s', async (route, currentUser) => {
    api.fetchMe.mockResolvedValue(currentUser)
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
          VideoUploadQueue: { template: '<div class="queue-stub" />' },
          BaseModal: { template: '<div class="modal-stub"><slot /></div>' },
        },
      },
    })
    await flushPromises()

    const sidebar = wrapper.get('.context-sidebar')
    expect(sidebar.text()).toContain('媒体概览')
    expect(sidebar.text()).toContain('我的图片')
    expect(sidebar.text()).toContain('我的视频')
    expect(sidebar.text()).toContain('团队')
    expect(sidebar.text()).toContain('所有分组')
    expect(sidebar.text()).toContain('账户与密钥')
    expect(sidebar.text()).toContain('视频上传中心')
    expect(sidebar.text()).toContain('退出登录')
    expect(sidebar.findAll('.nav-upload-center')).toHaveLength(1)
    expect(sidebar.findAll('[aria-current="page"]')).toHaveLength(1)

    if (currentUser.role === 'admin') {
      expect(sidebar.text()).toContain('全站图片')
      expect(sidebar.text()).toContain('全站视频')
      expect(sidebar.text()).toContain('管理中心')
    } else {
      expect(sidebar.text()).not.toContain('全站图片')
      expect(sidebar.text()).not.toContain('全站视频')
      expect(sidebar.text()).not.toContain('管理中心')
    }

    await sidebar.get('.nav-upload-center').trigger('click')
    expect(wrapper.find('.modal-stub').exists()).toBe(true)
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
          VideoView: {
            props: ['scope'],
            template: '<div class="video-scope-stub" :data-scope="scope" />',
          },
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

    window.location.hash = '#/my-videos'
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await flushPromises()

    expect(window.location.hash).toBe('#/videos')
    expect(wrapper.get('.video-scope-stub').attributes('data-scope')).toBe('mine')
    wrapper.unmount()
  })

  it.each([
    ['my-images', 'gallery-scope-stub'],
    ['my-videos', 'video-scope-stub'],
  ])('preserves the administrator #%s bookmark until login resolves the role', async (route, scopeStub) => {
    api.getToken.mockReturnValue(null)
    window.location.hash = `#/${route}`
    const wrapper = mount(App, {
      global: {
        stubs: {
          AppIcon: { template: '<i />' },
          HomeView: true,
          GalleryView: {
            props: ['scope'],
            template: '<div class="gallery-scope-stub" :data-scope="scope" />',
          },
          VideoView: {
            props: ['scope'],
            template: '<div class="video-scope-stub" :data-scope="scope" />',
          },
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

    expect(window.location.hash).toBe(`#/${route}`)
    await wrapper.get('.auth-stub').trigger('click')
    await flushPromises()

    expect(window.location.hash).toBe(`#/${route}`)
    expect(wrapper.get(`.${scopeStub}`).attributes('data-scope')).toBe('mine')
    wrapper.unmount()
  })

  it('keeps the account page mounted while a one-time credential response is pending', async () => {
    window.location.hash = '#/account'
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
          AccountView: {
            emits: ['credential-busy'],
            template: `
              <div class="account-stub">
                <button class="begin-credential" @click="$emit('credential-busy', true)">begin</button>
                <button class="finish-credential" @click="$emit('credential-busy', false)">finish</button>
              </div>
            `,
          },
          AuthView: true,
          UiFeedback: true,
          VideoUploadQueue: true,
          BaseModal: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('.begin-credential').trigger('click')
    expect(wrapper.get('.workspace-shell').attributes('inert')).toBeDefined()
    expect(wrapper.get('.workspace-shell').attributes('aria-busy')).toBe('true')

    const pushState = vi.spyOn(window.history, 'pushState')
    window.location.hash = '#/overview'
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await flushPromises()
    expect(pushState).toHaveBeenCalledWith(null, '', '#/account')
    expect(window.location.hash).toBe('#/account')

    const overview = wrapper.findAll('.side-nav button')
      .find(button => button.text().includes('媒体概览'))
    const logout = wrapper.get('.sidebar-user-logout')
    await overview.trigger('click')
    await logout.trigger('click')

    expect(window.location.hash).toBe('#/account')
    expect(wrapper.find('.account-stub').exists()).toBe(true)
    expect(api.setToken).not.toHaveBeenCalled()

    await wrapper.get('.finish-credential').trigger('click')
    await overview.trigger('click')
    expect(window.location.hash).toBe('#/overview')

    pushState.mockRestore()
    wrapper.unmount()
  })
})
