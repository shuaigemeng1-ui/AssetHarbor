// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  deleteImage: vi.fn(),
  fetchPublicConfig: vi.fn(),
  listImages: vi.fn(),
  listTeamImages: vi.fn(),
  updateImage: vi.fn(),
  uploadFile: vi.fn(),
}))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => ({
  confirmAction: vi.fn(),
  toast: vi.fn(),
}))

import GalleryView from '../components/GalleryView.vue'

describe('GalleryView image uploads', () => {
  const mountedWrappers = []

  beforeEach(() => {
    vi.clearAllMocks()
    api.listImages.mockResolvedValue({ items: [], total: 0 })
    api.listTeamImages.mockResolvedValue({ items: [], total: 0 })
    api.fetchPublicConfig.mockResolvedValue({ max_upload_size_mb: 10 })
  })

  afterEach(() => {
    mountedWrappers.splice(0).forEach(wrapper => wrapper.unmount())
  })

  function mountGallery(props = {}) {
    const wrapper = mount(GalleryView, {
      props: { user: { id: 1, role: 'user' }, ...props },
      global: {
        stubs: {
          AppIcon: { template: '<i class="icon-stub" />' },
          BaseModal: { template: '<div class="modal-stub"><slot /><slot name="footer" /></div>' },
          ImageResult: {
            props: ['item', 'selectable', 'selected'],
            emits: ['retry', 'select', 'remove-pending'],
            template: '<button class="image-result-stub" :data-status="item.status" :data-selected="String(selected)" @click="item.status === \'done\' ? $emit(\'select\') : $emit(\'retry\')">{{ item.status }}|{{ item.result?.code || item.file?.name }}|{{ item.error }}</button>',
          },
          ImageInspector: {
            props: ['item', 'groupable', 'teamId', 'canManageGroups'],
            template: '<aside class="inspector-stub" :data-code="item.code" :data-groupable="String(groupable)" :data-can-manage-groups="String(canManageGroups)" :data-team-id="teamId == null ? \'personal\' : String(teamId)" />',
          },
        },
      },
    })
    mountedWrappers.push(wrapper)
    return wrapper
  }

  async function openUpload(wrapper) {
    if (!wrapper.find('input[type="file"]').exists()) {
      await wrapper.get('.library-upload-button').trigger('click')
    }
  }

  async function selectFile(wrapper, filename = 'stamp.png') {
    await openUpload(wrapper)
    const file = new File(['png'], filename, { type: 'image/png' })
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
  }

  async function selectFiles(wrapper, files) {
    await openUpload(wrapper)
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: files, configurable: true })
    await input.trigger('change')
  }

  it('opens a one-shot upload request and marks it consumed', async () => {
    const wrapper = mountGallery({ openUpload: true })
    await flushPromises()

    expect(wrapper.find('input[type="file"]').exists()).toBe(true)
    expect(wrapper.emitted('upload-request-consumed')).toHaveLength(1)
  })

  it('requests and labels administrator global and personal scopes explicitly', async () => {
    const admin = { id: 99, username: 'admin', role: 'admin' }
    const globalView = mountGallery({ user: admin, scope: 'all' })
    await flushPromises()

    expect(globalView.get('.library-title h1').text()).toBe('全站图片')
    expect(globalView.get('.library-upload-button').text()).toContain('上传到我的个人空间')
    expect(api.listImages).toHaveBeenCalledWith({ limit: 12, offset: 0, q: '', scope: 'all' })

    const personalView = mountGallery({ user: admin, scope: 'mine' })
    await flushPromises()

    expect(personalView.get('.library-title h1').text()).toBe('我的图片')
    expect(personalView.get('.library-upload-button').text()).toContain('上传到我的个人空间')
    expect(api.listImages).toHaveBeenCalledWith({ limit: 12, offset: 0, q: '', scope: 'mine' })
  })

  it('uses compact team chrome when embedded and waits for an explicit card selection', async () => {
    api.listTeamImages.mockResolvedValue({
      items: [{ code: 'team-image', owner_id: 1, team_id: 42, visibility: 'public' }],
      total: 1,
    })
    const wrapper = mountGallery({ teamId: 42, embedded: true, canManage: true })
    await flushPromises()

    expect(wrapper.classes()).toContain('asset-library-embedded')
    expect(wrapper.find('.library-heading').exists()).toBe(false)
    expect(wrapper.get('.image-result-stub').attributes('data-selected')).toBe('false')
    expect(wrapper.find('.inspector-stub').exists()).toBe(false)
  })

  it('keeps a completed embedded upload unselected until the user opens it', async () => {
    api.uploadFile.mockResolvedValue({
      code: 'team-upload', name: 'team.png', original_filename: 'team.png',
      visibility: 'public', content_type: 'image/png', size: 128, url: '/i/team-upload', owner_id: 1, team_id: 42,
    })
    const wrapper = mountGallery({ teamId: 42, embedded: true, canManage: true })
    await flushPromises()
    await selectFile(wrapper, 'team.png')
    await flushPromises()

    expect(wrapper.get('.image-result-stub').attributes('data-selected')).toBe('false')
    expect(wrapper.find('.inspector-stub').exists()).toBe(false)
  })

  it('reactively removes the temporary card when the upload completes', async () => {
    let finishUpload
    api.uploadFile.mockImplementation(() => new Promise(resolve => { finishUpload = resolve }))

    const wrapper = mountGallery()
    await flushPromises()
    await openUpload(wrapper)
    expect(wrapper.get('.vis-select').element.value).toBe('private')
    await selectFile(wrapper)

    expect(wrapper.get('.image-result-stub').attributes('data-status')).toBe('uploading')

    finishUpload({
      code: 'image-code',
      name: 'stamp.png',
      original_filename: 'stamp.png',
      visibility: 'public',
      content_type: 'image/png',
      size: 128,
      url: '/i/image-code',
      owner_id: 1,
    })
    await flushPromises()

    expect(api.uploadFile).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.pending-grid').exists()).toBe(false)
    expect(wrapper.findAll('.image-result-stub')).toHaveLength(1)
    expect(wrapper.get('.image-result-stub').text()).toContain('image-code')
    expect(wrapper.get('.inspector-stub').attributes('data-code')).toBe('image-code')
    expect(wrapper.text()).toContain('1 张')
  })

  it('reactively changes the temporary card to an error state', async () => {
    api.uploadFile.mockRejectedValue(new Error('network failed'))
    const wrapper = mountGallery()
    await flushPromises()
    await selectFile(wrapper, 'failed.png')
    await flushPromises()

    const card = wrapper.get('.image-result-stub')
    expect(card.attributes('data-status')).toBe('error')
    expect(card.text()).toContain('network failed')
    expect(wrapper.text()).toContain('0 张')
  })

  it('retries a failed task with its original context and removes it after success', async () => {
    api.uploadFile
      .mockRejectedValueOnce(new Error('temporary network error'))
      .mockResolvedValueOnce({
        code: 'retry-code', name: 'stamp.png', original_filename: 'stamp.png', visibility: 'public',
        content_type: 'image/png', size: 128, url: '/i/retry-code', owner_id: 1,
      })
    const wrapper = mountGallery()
    await flushPromises()
    await selectFile(wrapper)
    await flushPromises()

    expect(wrapper.get('.image-result-stub').attributes('data-status')).toBe('error')
    await wrapper.get('.image-result-stub').trigger('click')
    await flushPromises()

    expect(api.uploadFile).toHaveBeenCalledTimes(2)
    expect(api.uploadFile.mock.calls[1][1]).toEqual({ name: '', visibility: 'private', teamId: null })
    expect(wrapper.find('.pending-grid').exists()).toBe(false)
    expect(wrapper.text()).toContain('retry-code')
    expect(wrapper.text()).toContain('1 张')
  })

  it('scopes inspector group actions to team media or the admin\'s own personal media', async () => {
    api.listImages.mockResolvedValue({
      items: [
        { code: 'admin-own', owner_id: 99, team_id: null, visibility: 'private' },
        { code: 'other-personal', owner_id: 7, team_id: null, visibility: 'private' },
        { code: 'team-media', owner_id: 7, team_id: 42, visibility: 'private' },
      ],
      total: 3,
    })
    const wrapper = mountGallery({ user: { id: 99, role: 'admin' } })
    await flushPromises()

    const cards = wrapper.findAll('.image-result-stub')
    expect(wrapper.get('.inspector-stub').attributes('data-groupable')).toBe('true')
    await cards[1].trigger('click')
    expect(wrapper.get('.inspector-stub').attributes('data-code')).toBe('other-personal')
    expect(wrapper.get('.inspector-stub').attributes('data-groupable')).toBe('false')
    await cards[2].trigger('click')
    expect(wrapper.get('.inspector-stub').attributes('data-code')).toBe('team-media')
    expect(wrapper.get('.inspector-stub').attributes('data-team-id')).toBe('42')
    expect(wrapper.get('.inspector-stub').attributes('data-can-manage-groups')).toBe('true')
  })

  it('does not grant team group management just because the user owns the image', async () => {
    api.listTeamImages.mockResolvedValue({
      items: [{ code: 'owned-team-image', owner_id: 1, team_id: 42, visibility: 'private' }],
      total: 1,
    })
    const wrapper = mountGallery({ teamId: 42, canManage: false })
    await flushPromises()

    expect(wrapper.get('.inspector-stub').attributes('data-can-manage-groups')).toBe('false')
  })

  it('closes the responsive inspector with Escape unless a modal owns the key', async () => {
    api.listImages.mockResolvedValue({
      items: [{ code: 'drawer-image', owner_id: 1, visibility: 'public' }],
      total: 1,
    })
    const wrapper = mountGallery()
    await flushPromises()
    await wrapper.get('.image-result-stub').trigger('click')
    expect(wrapper.classes()).toContain('inspector-open')
    expect(wrapper.get('.inspector-stub').attributes('role')).toBe('dialog')
    expect(wrapper.get('.inspector-stub').attributes('aria-modal')).toBe('true')

    const nestedModal = document.createElement('div')
    nestedModal.className = 'base-modal-panel'
    document.body.appendChild(nestedModal)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.classes()).toContain('inspector-open')
    nestedModal.remove()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.classes()).not.toContain('inspector-open')
  })

  it('uses a drawer at 1366px after accounting for the persistent sidebar', async () => {
    const originalInnerWidth = window.innerWidth
    const originalMatchMedia = window.matchMedia
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1366 })
    window.matchMedia = vi.fn(query => ({
      matches: query === '(max-width: 1408px)',
      media: query,
      onchange: null,
    }))
    try {
      api.listImages.mockResolvedValue({
        items: [{ code: 'sidebar-safe-image', owner_id: 1, visibility: 'public' }],
        total: 1,
      })
      const wrapper = mountGallery()
      await flushPromises()
      expect(wrapper.get('.inspector-stub').attributes('aria-hidden')).toBe('true')
      expect(wrapper.get('.inspector-stub').attributes('inert')).toBe('')
      await wrapper.get('.image-result-stub').trigger('click')

      expect(window.matchMedia).toHaveBeenCalledWith('(max-width: 1408px)')
      expect(wrapper.get('.inspector-stub').attributes('role')).toBe('dialog')
      expect(wrapper.get('.inspector-stub').attributes('aria-modal')).toBe('true')
      expect(wrapper.get('.inspector-stub').attributes('aria-hidden')).toBeUndefined()
      expect(wrapper.get('.inspector-stub').attributes('inert')).toBeUndefined()
    } finally {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: originalInnerWidth })
      window.matchMedia = originalMatchMedia
    }
  })

  it('rejects an oversized image before making an upload request', async () => {
    const wrapper = mountGallery()
    await flushPromises()
    const file = new File(['x'], 'oversized.png', { type: 'image/png' })
    Object.defineProperty(file, 'size', { value: 11 * 1024 * 1024 })

    await selectFiles(wrapper, [file])
    await flushPromises()

    expect(api.uploadFile).not.toHaveBeenCalled()
    expect(wrapper.get('.image-result-stub').attributes('data-status')).toBe('error')
    expect(wrapper.get('.image-result-stub').text()).toContain('10 MB')
    await wrapper.get('.image-result-stub').trigger('click')
    expect(api.uploadFile).not.toHaveBeenCalled()
  })

  it('shows every selected file immediately and uploads with at most three workers', async () => {
    let active = 0
    let maximum = 0
    const resolvers = []
    api.uploadFile.mockImplementation(file => new Promise(resolve => {
      active++
      maximum = Math.max(maximum, active)
      resolvers.push(() => {
        active--
        resolve({
          code: file.name, name: file.name, original_filename: file.name,
          visibility: 'private', content_type: 'image/png', size: file.size,
          url: `/i/${file.name}`, owner_id: 1,
        })
      })
    }))
    const wrapper = mountGallery()
    await flushPromises()
    const files = Array.from({ length: 5 }, (_, index) => (
      new File([String(index)], `image-${index}.png`, { type: 'image/png' })
    ))

    await selectFiles(wrapper, files)
    await vi.waitFor(() => expect(api.uploadFile).toHaveBeenCalledTimes(3))
    expect(wrapper.findAll('.image-result-stub')).toHaveLength(5)

    for (let index = 0; index < files.length; index++) {
      await vi.waitFor(() => expect(resolvers[index]).toBeTypeOf('function'))
      resolvers[index]()
      await flushPromises()
    }

    expect(maximum).toBe(3)
    expect(api.uploadFile).toHaveBeenCalledTimes(5)
    expect(wrapper.find('.pending-grid').exists()).toBe(false)
  })

  it('keeps the three-upload ceiling across overlapping file selections', async () => {
    let active = 0
    let maximum = 0
    const resolvers = []
    api.uploadFile.mockImplementation(file => new Promise(resolve => {
      active++
      maximum = Math.max(maximum, active)
      resolvers.push(() => {
        active--
        resolve({
          code: file.name, name: file.name, original_filename: file.name,
          visibility: 'private', content_type: 'image/png', size: file.size,
          url: `/i/${file.name}`, owner_id: 1,
        })
      })
    }))
    const wrapper = mountGallery()
    await flushPromises()
    const first = Array.from({ length: 4 }, (_, index) => (
      new File([`a${index}`], `first-${index}.png`, { type: 'image/png' })
    ))
    const second = Array.from({ length: 4 }, (_, index) => (
      new File([`b${index}`], `second-${index}.png`, { type: 'image/png' })
    ))

    await selectFiles(wrapper, first)
    await vi.waitFor(() => expect(api.uploadFile).toHaveBeenCalledTimes(3))
    await selectFiles(wrapper, second)
    await flushPromises()
    expect(api.uploadFile).toHaveBeenCalledTimes(3)

    for (let index = 0; index < 8; index++) {
      await vi.waitFor(() => expect(resolvers[index]).toBeTypeOf('function'))
      resolvers[index]()
      await flushPromises()
    }

    expect(maximum).toBe(3)
    expect(api.uploadFile).toHaveBeenCalledTimes(8)
  })

  it('routes retries through the same component-level concurrency queue', async () => {
    const resolvers = []
    api.uploadFile
      .mockRejectedValueOnce(new Error('temporary failure'))
      .mockImplementation(file => new Promise(resolve => {
        resolvers.push(() => resolve({
          code: file.name, name: file.name, original_filename: file.name,
          visibility: 'private', content_type: 'image/png', size: file.size,
          url: `/i/${file.name}`, owner_id: 1,
        }))
      }))
    const wrapper = mountGallery()
    await flushPromises()
    await selectFile(wrapper, 'retry-me.png')
    await vi.waitFor(() => expect(wrapper.get('[data-status="error"]')).toBeTruthy())

    const activeFiles = Array.from({ length: 3 }, (_, index) => (
      new File([String(index)], `active-${index}.png`, { type: 'image/png' })
    ))
    await selectFiles(wrapper, activeFiles)
    await vi.waitFor(() => expect(api.uploadFile).toHaveBeenCalledTimes(4))

    await wrapper.get('[data-status="error"]').trigger('click')
    await flushPromises()
    expect(api.uploadFile).toHaveBeenCalledTimes(4)

    resolvers[0]()
    await vi.waitFor(() => expect(api.uploadFile).toHaveBeenCalledTimes(5))
  })
})
