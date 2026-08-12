// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import BaseModal from '../components/BaseModal.vue'

describe('BaseModal focus and nested scroll locking', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    document.body.classList.remove('modal-open')
  })

  it('traps focus, restores it, and retains the body lock while a nested modal remains', async () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()

    const first = mount(BaseModal, {
      props: { title: '第一层', labelledBy: 'first-title' },
      slots: { default: '<button data-first>第一项</button><button data-last>最后一项</button>' },
    })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(document.body.classList.contains('modal-open')).toBe(true)

    document.querySelector('[data-last]').focus()
    document.querySelector('[data-last]').dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Tab', bubbles: true, cancelable: true,
    }))
    expect(document.activeElement).toBe(document.querySelector('.base-modal-close'))

    const second = mount(BaseModal, {
      props: {
        title: '危险确认', labelledBy: 'second-title', dialogRole: 'alertdialog',
        initialFocus: '[data-cancel]',
      },
      slots: { default: '<button data-confirm>删除</button><button data-cancel>取消</button>' },
    })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(document.activeElement).toBe(document.querySelector('[data-cancel]'))

    second.unmount()
    expect(document.body.classList.contains('modal-open')).toBe(true)
    first.unmount()
    expect(document.body.classList.contains('modal-open')).toBe(false)
    expect(document.activeElement).toBe(trigger)
  })
})
