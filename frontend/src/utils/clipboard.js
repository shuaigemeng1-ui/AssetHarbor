/**
 * Copy text to the clipboard.
 *
 * Uses the async Clipboard API when available (HTTPS/localhost secure
 * contexts), otherwise falls back to a hidden textarea + execCommand,
 * which works on plain-HTTP deployments too.
 *
 * @returns {Promise<boolean>} true when the copy succeeded
 */
export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fall through to the execCommand fallback
  }

  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  } catch {
    return false
  }
}
