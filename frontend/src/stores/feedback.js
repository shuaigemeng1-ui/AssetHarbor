import { reactive } from 'vue'

let nextToastId = 1
let pendingConfirm = null

export const feedback = reactive({
  toasts: [],
  confirm: null,
})

export function toast(message, type = 'info', duration = 3600) {
  const id = nextToastId++
  feedback.toasts.push({ id, message, type })
  window.setTimeout(() => dismissToast(id), duration)
  return id
}

export function dismissToast(id) {
  const index = feedback.toasts.findIndex(item => item.id === id)
  if (index >= 0) feedback.toasts.splice(index, 1)
}

export function confirmAction({ title = '请确认', message, confirmText = '确认', danger = false } = {}) {
  if (pendingConfirm) pendingConfirm(false)
  feedback.confirm = { title, message, confirmText, danger }
  return new Promise(resolve => {
    pendingConfirm = resolve
  })
}

export function resolveConfirm(result) {
  pendingConfirm?.(result)
  pendingConfirm = null
  feedback.confirm = null
}
