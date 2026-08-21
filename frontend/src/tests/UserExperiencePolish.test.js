// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  deleteImage: vi.fn(),
  fetchPublicConfig: vi.fn(),
  getSignedLink: vi.fn(),
  listImages: vi.fn(),
  listTeamImages: vi.fn(),
  updateImage: vi.fn(),
  uploadFile: vi.fn(),
}))
const feedback = vi.hoisted(() => ({
  confirmAction: vi.fn(),
  toast: vi.fn(),
}))
const clipboard = vi.hoisted(() => ({ copyText: vi.fn() }))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => feedback)
vi.mock('../utils/clipboard', () => clipboard)

import GalleryView from '../components/GalleryView.vue'
import ImageInspector from '../components/ImageInspector.vue'
import ImageResult from '../components/ImageResult.vue'
import UploadDropzone from '../components/UploadDropzone.vue'

const BaseModalStub = {
  name: 'BaseModal',
  props: ['title', 'description'],
  template: '<div data-test="modal" :data-title="title"><slot /><slot name="footer" /></div>',
}

describe('User Experience & Interaction Polish', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clipboard.copyText.mockResolvedValue(true)
    feedback.confirmAction.mockResolvedValue(true)
    api.fetchPublicConfig.mockResolvedValue({ max_upload_size_mb: 10 })
    api.listImages.mockResolvedValue({ items: [], total: 0 })
    api.listTeamImages.mockResolvedValue({ items: [], total: 0 })
  })

  describe('UploadDropzone clipboard paste', () => {
    it('emits files when user pastes files into the dropzone', async () => {
      const wrapper = mount(UploadDropzone)
      const file = new File(['pdf data'], 'doc.pdf', { type: 'application/pdf' })

      await wrapper.get('.drop').trigger('paste', {
        clipboardData: {
          files: [file],
          items: [],
        },
      })

      const emitted = wrapper.emitted('files')
      expect(emitted).toBeTruthy()
      expect(emitted[0][0]).toEqual([file])
    })

    it('emits files extracted from clipboard items when files array is empty', async () => {
      const wrapper = mount(UploadDropzone)
      const file = new File(['img data'], 'screenshot.png', { type: 'image/png' })
      const item = {
        kind: 'file',
        type: 'image/png',
        getAsFile: () => file,
      }

      await wrapper.get('.drop').trigger('paste', {
        clipboardData: {
          files: [],
          items: [item],
        },
      })

      const emitted = wrapper.emitted('files')
      expect(emitted).toBeTruthy()
      expect(emitted[0][0]).toEqual([file])
    })
  })

  describe('PDF Adaptive Labels in ImageInspector & ImageResult', () => {
    const pdfItem = {
      id: 88,
      code: 'manual-pdf',
      name: '技术规格说明书',
      original_filename: 'spec.pdf',
      size: 4096,
      content_type: 'application/pdf',
      visibility: 'public',
      url: '/i/manual-pdf',
      owner_id: 1,
      owner_username: 'bob',
      team_id: null,
    }

    it('adapts header, buttons, and preview actions for PDF in ImageInspector', async () => {
      const wrapper = mount(ImageInspector, {
        props: {
          item: pdfItem,
          user: { id: 1, username: 'bob', role: 'user' },
          canManage: true,
        },
        global: {
          stubs: {
            AppIcon: { template: '<i />' },
            BaseModal: BaseModalStub,
            CollectionPickerModal: { template: '<div />' },
          },
        },
      })

      expect(wrapper.attributes('aria-label')).toBe('PDF 文档详情')
      expect(wrapper.text()).toContain('PDF 文档详情')
      expect(wrapper.text()).toContain('技术规格说明书')
      expect(wrapper.text()).toContain('删除文档')
      expect(wrapper.text()).toContain('复制文档链接')

      // Check external viewer button
      const openBtn = wrapper.find('.pdf-open-btn')
      expect(openBtn.exists()).toBe(true)
      expect(openBtn.attributes('href')).toBe('/i/manual-pdf')

      // Check rename modal title
      const renameBtn = wrapper.findAll('button').find(b => b.text() === '重命名')
      await renameBtn.trigger('click')
      const modal = wrapper.findComponent(BaseModalStub)
      expect(modal.props('title')).toBe('重命名文档')
    })

    it('adapts labels and toasts for PDF in ImageResult', async () => {
      const wrapper = mount(ImageResult, {
        props: {
          item: { id: 'image-88', status: 'done', result: { ...pdfItem }, file: null },
          editable: true,
          deletable: true,
        },
        global: {
          stubs: {
            AppIcon: { template: '<i />' },
            BaseModal: BaseModalStub,
          },
        },
      })

      expect(wrapper.text()).toContain('PDF')
      expect(wrapper.text()).toContain('技术规格说明书')
      expect(wrapper.text()).toContain('复制文档链接')

      const copyBtn = wrapper.findAll('button').find(b => b.text() === '复制文档链接')
      await copyBtn.trigger('click')
      expect(feedback.toast).toHaveBeenCalledWith('文档链接已复制', 'success')
    })
  })

  describe('GalleryView keyboard navigation and clipboard handling', () => {
    it('navigates between media cards using ArrowRight and ArrowLeft', async () => {
      const items = [
        { id: 1, code: 'code-1', name: 'Item 1', visibility: 'public', content_type: 'image/png', url: '/i/code-1' },
        { id: 2, code: 'code-2', name: 'Item 2', visibility: 'public', content_type: 'image/png', url: '/i/code-2' },
        { id: 3, code: 'code-3', name: 'Item 3', visibility: 'public', content_type: 'image/png', url: '/i/code-3' },
      ]
      api.listImages.mockResolvedValue({ items, total: 3 })

      const wrapper = mount(GalleryView, {
        props: {
          user: { id: 1, username: 'admin', role: 'admin' },
        },
        global: {
          stubs: {
            AppIcon: { template: '<i />' },
            ImageInspector: {
              name: 'ImageInspector',
              props: ['item'],
              template: '<div class="inspector-stub">{{ item.name }}</div>',
            },
            ImageResult: {
              name: 'ImageResult',
              props: ['item', 'selected'],
              template: '<div class="result-stub" :class="{ selected }" @click="$emit(\'select\', item.result)">{{ item.result.name }}</div>',
            },
            BaseModal: BaseModalStub,
            UploadDropzone: { template: '<div class="drop-stub" />' },
          },
        },
      })

      await flushPromises()

      // Initially item 1 is selected
      expect(wrapper.find('.inspector-stub').text()).toBe('Item 1')

      // Press ArrowRight -> selects Item 2
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
      await flushPromises()
      expect(wrapper.find('.inspector-stub').text()).toBe('Item 2')

      // Press ArrowRight again -> selects Item 3
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
      await flushPromises()
      expect(wrapper.find('.inspector-stub').text()).toBe('Item 3')

      // Press ArrowLeft -> selects Item 2
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
      await flushPromises()
      expect(wrapper.find('.inspector-stub').text()).toBe('Item 2')

      // Press Escape -> closes inspector
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
      await flushPromises()
      expect(wrapper.find('.inspector-stub').exists()).toBe(false)
    })
  })
})
