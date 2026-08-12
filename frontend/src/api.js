export async function uploadFile(file) {
  const fd = new FormData()
  fd.append('file', file, file.name)
  const resp = await fetch('/api/upload', { method: 'POST', body: fd })
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) throw new Error(body.detail || `HTTP ${resp.status}`)
  return body
}
