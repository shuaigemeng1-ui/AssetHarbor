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
import ImagePreviewModal from '../components/ImagePreviewModal.vue'
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

  describe('PDF Adaptive Labels and Download in ImageInspector & ImageResult', () => {
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
      expect(wrapper.text()).toContain('下载文档')
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

    it('adapts labels, download and toasts for PDF in ImageResult', async () => {
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
      expect(wrapper.text()).toContain('下载')
      expect(wrapper.text()).toContain('复制文档链接')

      const copyBtn = wrapper.findAll('button').find(b => b.text().includes('复制文档链接'))
      await copyBtn.trigger('click')
      expect(feedback.toast).toHaveBeenCalledWith('文档链接已复制', 'success')
    })
  })

  describe('Private Status TTL Options in ImageInspector', () => {
    const privateItem = {
      id: 99,
      code: 'priv-img',
      name: '私密图片',
      original_filename: 'priv.png',
      size: 2048,
      content_type: 'image/png',
      visibility: 'private',
      url: '/i/priv-img',
      owner_id: 1,
      owner_username: 'bob',
      team_id: null,
    }

    it('provides TTL options and generates signed link with selected duration on click', async () => {
      api.getSignedLink.mockResolvedValue({ url: '/i/priv-img?sig=test7d', expires_at: '2026-08-29T12:00:00Z' })

      const wrapper = mount(ImageInspector, {
        props: {
          item: privateItem,
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
      await flushPromises()

      const ttlSelect = wrapper.find('.ttl-select')
      expect(ttlSelect.exists()).toBe(true)

      // Set to 7 days (604800)
      await ttlSelect.setValue(604800)

      const generateBtn = wrapper.findAll('button').find(b => b.text().includes('生成并复制'))
      await generateBtn.trigger('click')
      await flushPromises()

      expect(api.getSignedLink).toHaveBeenCalledWith('priv-img', 604800)
      expect(clipboard.copyText).toHaveBeenCalledWith('/i/priv-img?sig=test7d')
      expect(feedback.toast).toHaveBeenCalledWith('限时签名链接已复制', 'success')
    })
  })

  describe('ImagePreviewModal Component', () => {
    const imgItem = {
      id: 101,
      code: 'preview-hero',
      name: '横幅海报',
      original_filename: 'banner.png',
      size: 8192,
      content_type: 'image/png',
      visibility: 'public',
      url: '/i/preview-hero',
    }

    it('renders image, controls zoom, and triggers download', async () => {
      const wrapper = mount(ImagePreviewModal, {
        props: {
          item: imgItem,
          hasPrev: true,
          hasNext: true,
        },
        global: {
          stubs: {
            AppIcon: { template: '<i />' },
          },
        },
      })

      expect(wrapper.text()).toContain('横幅海报')
      expect(wrapper.text()).toContain('8 KB')
      expect(wrapper.text()).toContain('100%')

      const zoomInBtn = wrapper.find('button[title="放大 (+)"]')
      await zoomInBtn.trigger('click')
      expect(wrapper.text()).toContain('125%')

      const prevBtn = wrapper.find('.prev-btn')
      await prevBtn.trigger('click')
      expect(wrapper.emitted('prev')).toBeTruthy()

      const nextBtn = wrapper.find('.next-btn')
      await nextBtn.trigger('click')
      expect(wrapper.emitted('next')).toBeTruthy()
    })
  })

  describe('GalleryView multi-select, filter pills and batch toolbar', () => {
    const sampleItems = [
      { id: 1, code: 'img-1', name: '风景照.png', visibility: 'public', content_type: 'image/png', url: '/i/img-1', owner_id: 1 },
      { id: 2, code: 'pdf-2', name: '报告.pdf', visibility: 'private', content_type: 'application/pdf', url: '/i/pdf-2', owner_id: 1 },
      { id: 3, code: 'img-3', name: '海报.jpg', visibility: 'public', content_type: 'image/jpeg', url: '/i/img-3', owner_id: 1 },
    ]

    it('filters items when clicking filter pills', async () => {
      api.listImages.mockResolvedValue({ items: sampleItems, total: 3 })
      const wrapper = mount(GalleryView, {
        props: { user: { id: 1, username: 'admin', role: 'admin' } },
        global: {
          stubs: {
            AppIcon: { template: '<i />' },
            ImageInspector: { template: '<div />' },
            ImageResult: {
              props: ['item'],
              template: '<div class="card-stub">{{ item.result.name }}</div>',
            },
            BaseModal: BaseModalStub,
            UploadDropzone: { template: '<div />' },
            ImagePreviewModal: { template: '<div />' },
            CollectionPickerModal: { template: '<div />' },
          },
        },
      })
      await flushPromises()

      expect(wrapper.findAll('.card-stub').length).toBe(3)

      // Click PDF filter pill
      const pdfPill = wrapper.findAll('.filter-pill').find(p => p.text().includes('PDF 文档'))
      await pdfPill.trigger('click')
      expect(wrapper.findAll('.card-stub').length).toBe(1)
      expect(wrapper.find('.card-stub').text()).toBe('报告.pdf')

      // Click Private filter pill
      const privPill = wrapper.findAll('.filter-pill').find(p => p.text().includes('私密'))
      await privPill.trigger('click')
      expect(wrapper.findAll('.card-stub').length).toBe(1)
      expect(wrapper.find('.card-stub').text()).toBe('报告.pdf')

      // Click All filter pill
      const allPill = wrapper.findAll('.filter-pill').find(p => p.text().includes('全部'))
      await allPill.trigger('click')
      expect(wrapper.findAll('.card-stub').length).toBe(3)
    })

    it('shows floating batch bar on card check and supports batch operations', async () => {
      api.listImages.mockResolvedValue({ items: sampleItems, total: 3 })
      api.updateImage.mockResolvedValue({ visibility: 'private' })
      const wrapper = mount(GalleryView, {
        props: { user: { id: 1, username: 'admin', role: 'admin' } },
        global: {
          stubs: {
            AppIcon: { template: '<i />' },
            ImageInspector: { template: '<div />' },
            ImageResult: {
              props: ['item', 'checked'],
              template: '<div class="card-stub"><button class="chk-stub" @click="$emit(\'check\', { item: item.result })">check</button></div>',
            },
            BaseModal: BaseModalStub,
            UploadDropzone: { template: '<div />' },
            ImagePreviewModal: { template: '<div />' },
            CollectionPickerModal: { template: '<div />' },
          },
        },
      })
      await flushPromises()

      expect(wrapper.find('.floating-batch-bar').exists()).toBe(false)

      // Check first item
      await wrapper.findAll('.chk-stub')[0].trigger('click')
      expect(wrapper.find('.floating-batch-bar').exists()).toBe(true)
      expect(wrapper.find('.batch-bar-count').text()).toContain('1')

      // Select all via batch bar
      const selectAllBtn = wrapper.find('.batch-btn-link')
      await selectAllBtn.trigger('click')
      expect(wrapper.find('.batch-bar-count').text()).toContain('3')

      // Batch set private
      const setPrivateBtn = wrapper.findAll('.batch-action-btn').find(b => b.text().includes('设为私密'))
      await setPrivateBtn.trigger('click')
      await flushPromises()
      expect(api.updateImage).toHaveBeenCalled()
      expect(feedback.toast).toHaveBeenCalledWith(expect.stringContaining('已将'), 'success')
    })
  })
})
