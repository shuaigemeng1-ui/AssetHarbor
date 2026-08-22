/**
 * Universal media file download helper.
 * Triggers a browser native file download with specified filename.
 */
export function downloadMediaFile(url, filename = 'file') {
  if (!url) return
  const finalUrl = url.includes('?') ? `${url}&download=1` : `${url}?download=1`
  const link = document.createElement('a')
  link.href = finalUrl
  link.setAttribute('download', filename)
  link.rel = 'noopener noreferrer'
  link.target = '_blank'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}
