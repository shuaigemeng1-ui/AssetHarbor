// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import UploadDropzone from '../components/UploadDropzone.vue'

function liveFileList(initialFiles) {
  let files = [...initialFiles]
  return {
    get length() { return files.length },
    item(index) { return files[index] || null },
    [Symbol.iterator]() { return files[Symbol.iterator]() },
    clear() { files = [] },
  }
}

describe('UploadDropzone', () => {
  it('emits a stable snapshot before the file input is reset', async () => {
    const wrapper = mount(UploadDropzone)
    const file = new File(['image'], 'photo.png', { type: 'image/png' })
    const liveFiles = liveFileList([file])
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      get: () => liveFiles,
    })

    await input.trigger('change')
    liveFiles.clear()

    const emittedFiles = wrapper.emitted('files')[0][0]
    expect(Array.isArray(emittedFiles)).toBe(true)
    expect(emittedFiles).toEqual([file])
  })

  it('emits a stable snapshot before the drop event releases its files', async () => {
    const wrapper = mount(UploadDropzone)
    const file = new File(['video'], 'clip.mp4', { type: 'video/mp4' })
    const liveFiles = liveFileList([file])

    await wrapper.get('.drop').trigger('drop', { dataTransfer: { files: liveFiles } })
    liveFiles.clear()

    const emittedFiles = wrapper.emitted('files')[0][0]
    expect(Array.isArray(emittedFiles)).toBe(true)
    expect(emittedFiles).toEqual([file])
  })
})
