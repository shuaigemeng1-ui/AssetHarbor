// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import UploadCenterView from '../components/UploadCenterView.vue'
import { videoUploadState } from '../stores/videoUploads'

function mountView() {
  return mount(UploadCenterView, {
    attachTo: document.body,
    global: {
      stubs: {
        VideoUploadQueue: {
          props: { allScopes: Boolean },
          template: '<div class="queue-stub" :data-all-scopes="String(allScopes)" />',
        },
      },
    },
  })
}

describe('UploadCenterView', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    videoUploadState.tasks.splice(0)
    videoUploadState.restored = false
  })

  it('renders an independent all-scope upload task page', () => {
    videoUploadState.restored = true
    videoUploadState.tasks.push({ localId: 1, status: 'completed' })
    const wrapper = mountView()

    expect(wrapper.get('h1').text()).toBe('视频上传中心')
    expect(wrapper.text()).toContain('集中管理个人空间与团队空间的视频上传任务')
    expect(wrapper.text()).toContain('全部视频上传任务')
    expect(wrapper.get('.queue-stub').attributes('data-all-scopes')).toBe('true')
    expect(wrapper.get('[role="status"]').attributes('aria-live')).toBe('polite')
    expect(wrapper.text()).toContain('当前没有未完成的视频上传任务')
    expect(document.activeElement).toBe(wrapper.get('h1').element)
  })

  it('reports the existing unfinished upload count', async () => {
    videoUploadState.restored = true
    videoUploadState.tasks.push(
      { localId: 1, status: 'uploading' },
      { localId: 2, status: 'completed' },
    )
    const wrapper = mountView()

    expect(wrapper.get('.status-copy strong').text()).toBe('1')
    expect(wrapper.text()).toContain('当前有 1 个未完成的视频上传任务')

    videoUploadState.tasks.push({ localId: 3, status: 'manual_paused' })
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.status-copy strong').text()).toBe('2')
    expect(wrapper.text()).toContain('当前有 2 个未完成的视频上传任务')
  })

  it('distinguishes restoration from a genuinely empty task list', async () => {
    const wrapper = mountView()

    expect(wrapper.get('.upload-status-summary').attributes('aria-busy')).toBe('true')
    expect(wrapper.text()).toContain('正在恢复本地保存的视频上传任务')
    expect(wrapper.text()).toContain('正在恢复上传任务')
    expect(wrapper.find('.queue-stub').exists()).toBe(false)

    videoUploadState.restored = true
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.upload-status-summary').attributes('aria-busy')).toBeUndefined()
    expect(wrapper.text()).toContain('暂无视频上传任务')
    expect(wrapper.text()).toContain('当前没有未完成的视频上传任务')
    expect(wrapper.find('.queue-stub').exists()).toBe(false)
  })
})
