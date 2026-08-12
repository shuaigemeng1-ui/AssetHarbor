// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import VideoUploadQueue from '../components/VideoUploadQueue.vue'
import { videoUploadState } from '../stores/videoUploads'

describe('VideoUploadQueue', () => {
  afterEach(() => {
    videoUploadState.tasks.splice(0)
    videoUploadState.maxActiveSessions = 3
  })

  it('renders accessible progress and restored-file guidance', () => {
    videoUploadState.tasks.push({
      localId: 1,
      teamId: null,
      filename: 'restored.mp4',
      name: '',
      size: 100,
      chunkSize: 20,
      uploadedParts: [0, 1],
      chunkProgress: {},
      status: 'waiting_file',
      speed: 0,
      eta: Infinity,
      error: '',
    })

    const wrapper = mount(VideoUploadQueue)
    const progress = wrapper.get('[role="progressbar"]')

    expect(progress.attributes('aria-valuenow')).toBe('40')
    expect(wrapper.text()).toContain('等待重新选择文件')
    expect(wrapper.text()).toContain('浏览器不会保存视频本体')
  })

  it('shows all scopes, expiry, and an actionable retry for remote finalization', () => {
    videoUploadState.maxActiveSessions = 5
    videoUploadState.tasks.push(
      {
        localId: 1, teamId: null, filename: 'personal.mp4', name: '', size: 100,
        chunkSize: 20, uploadedParts: [], chunkProgress: {}, status: 'waiting_file',
        speed: 0, eta: Infinity, error: '', expiresAt: null,
      },
      {
        localId: 2, teamId: 42, filename: 'team.mp4', name: '', size: 100,
        chunkSize: 20, uploadedParts: [0], chunkProgress: {}, status: 'failed',
        serverStatus: 'finalizing', speed: 0, eta: Infinity,
        error: '服务端校验尚未完成', expiresAt: '2026-08-19T10:00:00Z',
      },
    )

    const personal = mount(VideoUploadQueue)
    expect(personal.text()).toContain('personal.mp4')
    expect(personal.text()).not.toContain('team.mp4')

    const global = mount(VideoUploadQueue, { props: { allScopes: true } })
    expect(global.text()).toContain('个人空间')
    expect(global.text()).toContain('团队 #42')
    expect(global.text()).toContain('服务端最多同时保留 5 个未完成会话')
    expect(global.text()).toContain('会话有效期至')
    expect(global.findAll('button').some(button => button.text() === '重试')).toBe(true)
  })
})
