// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import VideoUploadQueue from '../components/VideoUploadQueue.vue'
import { videoUploadState } from '../stores/videoUploads'

describe('VideoUploadQueue', () => {
  afterEach(() => videoUploadState.tasks.splice(0))

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
})
