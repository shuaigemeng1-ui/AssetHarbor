// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
  beforeEach(() => {
    vi.clearAllMocks()
    api.listImages.mockResolvedValue({ items: [], total: 0 })
    api.listTeamImages.mockResolvedValue({ items: [], total: 0 })
    api.fetchPublicConfig.mockResolvedValue({ default_visibility: 'private', max_upload_size_mb: 10 })
  })

  function mountGallery(props = {}) {
    return mount(GalleryView, {
      props: { user: { id: 1, role: 'user' }, ...props },
      global: {
        stubs: {
          ImageResult: {
            props: ['item', 'groupable'],
            emits: ['retry', 'add-to-group'],
            template: '<button class="image-result-stub" :data-status="item.status" :data-groupable="String(groupable)" @click="$emit(\'retry\')">{{ item.status }}|{{ item.result?.code || item.file?.name }}|{{ item.error }}<span v-if="groupable" class="group-trigger" @click.stop="$emit(\'add-to-group\')">group</span></button>',
          },
          CollectionPickerModal: {
            props: ['media', 'teamId', 'userId', 'canManage'],
            template: '<div class="picker-stub" :data-code="media.code" :data-team-id="teamId == null ? \'personal\' : String(teamId)" />',
          },
        },
      },
    })
  }

  async function selectFile(wrapper, filename = 'stamp.png') {
    const file = new File(['png'], filename, { type: 'image/png' })
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
  }

  it('reactively removes the temporary card when the upload completes', async () => {
    let finishUpload
    api.uploadFile.mockImplementation(() => new Promise(resolve => { finishUpload = resolve }))

    const wrapper = mountGallery()
    await flushPromises()
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
        code: 'retry-code', name: 'stamp.png', original_filename: 'stamp.png', visibility: 'private',
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

  it('scopes admin group actions to team media or the admin\'s own personal media', async () => {
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
    expect(cards.map(card => card.attributes('data-groupable'))).toEqual(['true', 'false', 'true'])

    await cards[2].get('.group-trigger').trigger('click')
    expect(wrapper.get('.picker-stub').attributes('data-code')).toBe('team-media')
    expect(wrapper.get('.picker-stub').attributes('data-team-id')).toBe('42')
  })
})
