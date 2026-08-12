let modalLockCount = 0

export function acquireModalLock() {
  modalLockCount++
  document.body.classList.add('modal-open')
}

export function releaseModalLock() {
  modalLockCount = Math.max(0, modalLockCount - 1)
  if (!modalLockCount) document.body.classList.remove('modal-open')
}
