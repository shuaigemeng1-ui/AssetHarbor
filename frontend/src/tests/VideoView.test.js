// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  deleteVideo: vi.fn(),
  fetchPublicConfig: vi.fn(),
  listTeamVideos: vi.fn(),
  listVideos: vi.fn(),
  updateVideo: vi.fn(),
}))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => ({
  confirmAction: vi.fn(),
  toast: vi.fn(),
}))
vi.mock('../stores/videoUploads', () => ({
  addVideoFiles: vi.fn(() => []),
  VIDEO_ACCEPT: 'video/*',
  videoUploadState: { tasks: [] },
}))

import VideoView from '../components/VideoView.vue'

describe('VideoView media group scope', () => {
  const mountedWrappers = []

  beforeEach(() => {
    vi.clearAllMocks()
    api.listVideos.mockResolvedValue({ items: [], total: 0 })
    api.listTeamVideos.mockResolvedValue({ items: [], total: 0 })
    api.fetchPublicConfig.mockResolvedValue({ max_video_size_mb: 2048, video_chunk_size_mb: 8 })
  })

  afterEach(() => {
    mountedWrappers.splice(0).forEach(wrapper => wrapper.unmount())
  })

  function mountVideos(props = {}) {
    const wrapper = mount(VideoView, {
      props: { user: { id: 1, role: 'user' }, ...props },
      global: {
        stubs: {
          UploadDropzone: {
            props: ['ariaLabel'],
            template: '<div class="dropzone-stub" :aria-label="ariaLabel" />',
          },
          VideoUploadQueue: true,
          VideoPlayerModal: true,
          VideoCard: {
            props: ['item', 'selectable', 'selected'],
            emits: ['select'],
            template: '<button class="video-card-stub" :data-code="item.code" :data-selectable="String(selectable)" :data-selected="String(selected)" @click="$emit(\'select\')">select</button>',
          },
          VideoInspector: {
            props: ['item', 'groupable', 'teamId', 'canManageGroups'],
            template: '<aside class="inspector-stub" :data-code="item.code" :data-groupable="String(groupable)" :data-can-manage-groups="String(canManageGroups)" :data-team-id="teamId == null ? \'personal\' : String(teamId)" />',
          },
        },
      },
    })
    mountedWrappers.push(wrapper)
    return wrapper
  }

  it('scopes admin group actions to team media or the admin\'s own personal media', async () => {
    api.listVideos.mockResolvedValue({
      items: [
        { code: 'admin-own', owner_id: 99, team_id: null, visibility: 'private' },
        { code: 'other-personal', owner_id: 7, team_id: null, visibility: 'private' },
        { code: 'team-media', owner_id: 7, team_id: 42, visibility: 'private' },
      ],
      total: 3,
    })
    const wrapper = mountVideos({ user: { id: 99, role: 'admin' } })
    await flushPromises()
    expect(wrapper.classes()).toContain('asset-library')
    expect(wrapper.get('.library-title h1').text()).toBe('全站视频')
    expect(wrapper.get('.media-grid.asset-grid').attributes('aria-label')).toBe('视频列表')

    const cards = wrapper.findAll('.video-card-stub')
    expect(cards.every(card => card.attributes('data-selectable') !== undefined)).toBe(true)
    expect(wrapper.get('.inspector-stub').attributes('data-groupable')).toBe('true')
    await cards[1].trigger('click')
    expect(wrapper.get('.inspector-stub').attributes('data-code')).toBe('other-personal')
    expect(wrapper.get('.inspector-stub').attributes('data-groupable')).toBe('false')
    await cards[2].trigger('click')
    expect(wrapper.get('.inspector-stub').attributes('data-code')).toBe('team-media')
    expect(wrapper.get('.inspector-stub').attributes('data-team-id')).toBe('42')
  })

  it('uses the canonical media-library skeleton and opens uploads on demand', async () => {
    api.listVideos.mockResolvedValue({
      items: [{ code: 'video-1', owner_id: 1, visibility: 'public' }],
      total: 1,
    })
    const wrapper = mountVideos()
    await flushPromises()

    expect(wrapper.get('.asset-library-main .library-title h1').text()).toBe('我的视频')
    expect(wrapper.get('.library-title span').text()).toBe('1 个')
    expect(wrapper.get('.library-toolbar input[aria-label="搜索视频"]').exists()).toBe(true)
    expect(document.body.querySelector('[aria-label="选择或拖拽视频上传"]')).toBeNull()

    await wrapper.get('.library-upload-button').trigger('click')
    expect(document.body.querySelector('[aria-label="选择或拖拽视频上传"]')).not.toBeNull()
    expect(document.body.querySelector('.vis-select').value).toBe('public')
  })
})
