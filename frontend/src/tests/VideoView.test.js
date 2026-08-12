// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
}))

import VideoView from '../components/VideoView.vue'

describe('VideoView media group scope', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listVideos.mockResolvedValue({ items: [], total: 0 })
    api.listTeamVideos.mockResolvedValue({ items: [], total: 0 })
    api.fetchPublicConfig.mockResolvedValue({ default_visibility: 'private' })
  })

  function mountVideos(props = {}) {
    return mount(VideoView, {
      props: { user: { id: 1, role: 'user' }, ...props },
      global: {
        stubs: {
          UploadDropzone: true,
          VideoUploadQueue: true,
          VideoPlayerModal: true,
          VideoCard: {
            props: ['item', 'groupable'],
            emits: ['add-to-group'],
            template: '<div class="video-card-stub" :data-code="item.code" :data-groupable="String(groupable)"><button v-if="groupable" class="group-trigger" @click="$emit(\'add-to-group\')">group</button></div>',
          },
          CollectionPickerModal: {
            props: ['media', 'teamId', 'userId', 'canManage'],
            template: '<div class="picker-stub" :data-code="media.code" :data-team-id="teamId == null ? \'personal\' : String(teamId)" />',
          },
        },
      },
    })
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

    const cards = wrapper.findAll('.video-card-stub')
    expect(cards.map(card => card.attributes('data-groupable'))).toEqual(['true', 'false', 'true'])

    await cards[2].get('.group-trigger').trigger('click')
    expect(wrapper.get('.picker-stub').attributes('data-code')).toBe('team-media')
    expect(wrapper.get('.picker-stub').attributes('data-team-id')).toBe('42')
  })
})
