const TOKEN_KEY = 'oss_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export async function request(path, options = {}) {
  const { suppressUnauthorized = false, ...fetchOptions } = options
  const headers = { ...(fetchOptions.headers || {}) }
  const token = getToken()
  if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`

  const resp = await fetch(path, { ...fetchOptions, headers })
  if (resp.status === 401 && !path.startsWith('/api/auth/') && !suppressUnauthorized) {
    setToken(null)
    window.dispatchEvent(new Event('oss:unauthorized'))
    throw new Error('登录已过期，请重新登录')
  }
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    const error = new Error(body.detail || `HTTP ${resp.status}`)
    error.status = resp.status
    error.body = body
    throw error
  }
  return body
}

// --- auth -----------------------------------------------------------------

export function login(username, password) {
  return request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username, password }),
  })
}

export function register(username, password) {
  return request('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function fetchMe() {
  return request('/api/auth/me')
}

export function changePassword(oldPassword, newPassword) {
  return request('/api/auth/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  })
}

// --- API keys ---------------------------------------------------------------

export function listApiKeys() {
  return request('/api/keys')
}

export function createApiKey(name = '') {
  return request('/api/keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function rotateApiKey(id) {
  return request(`/api/keys/${id}/rotate`, { method: 'POST' })
}

export function deleteApiKey(id) {
  return request(`/api/keys/${id}`, { method: 'DELETE' })
}

// --- images ---------------------------------------------------------------

export function uploadFile(file, { name = '', visibility = 'public', teamId = null } = {}) {
  const fd = new FormData()
  fd.append('file', file, file.name)
  fd.append('visibility', visibility)
  if (name) fd.append('name', name)
  if (teamId) fd.append('team_id', String(teamId))
  return request('/api/upload', { method: 'POST', body: fd })
}

export function listImages({ limit = 20, offset = 0, q = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (q) params.set('q', q)
  return request(`/api/images?${params}`)
}

export function getSignedLink(code, ttl) {
  const params = new URLSearchParams()
  if (ttl) params.set('ttl', String(ttl))
  const qs = params.toString()
  return request(`/api/images/${code}/link${qs ? `?${qs}` : ''}`)
}

export function deleteImage(code) {
  return request(`/api/images/${code}`, { method: 'DELETE' })
}

export function updateImage(code, { name, visibility } = {}) {
  return request(`/api/images/${code}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, visibility }),
  })
}

// --- videos ---------------------------------------------------------------

export function createVideoUpload(payload, { signal, token, suppressUnauthorized = false } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  return request('/api/video-uploads', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
    suppressUnauthorized,
  })
}

export function getVideoUpload(uploadId) {
  return request(`/api/video-uploads/${uploadId}`)
}

export function cancelVideoUpload(uploadId, { token, suppressUnauthorized = false } = {}) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  return request(`/api/video-uploads/${uploadId}`, {
    method: 'DELETE',
    headers,
    suppressUnauthorized,
  })
}

export function completeVideoUpload(uploadId) {
  return request(`/api/video-uploads/${uploadId}/complete`, { method: 'POST' })
}

export function uploadVideoPart(uploadId, partNumber, blob, {
  start,
  total,
  sha256,
  onProgress,
} = {}) {
  const xhr = new XMLHttpRequest()
  const promise = new Promise((resolve, reject) => {
    xhr.open('PUT', `/api/video-uploads/${uploadId}/parts/${partNumber}`)
    const token = getToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    xhr.setRequestHeader('Content-Range', `bytes ${start}-${start + blob.size - 1}/${total}`)
    xhr.setRequestHeader('X-Chunk-SHA256', sha256)

    xhr.upload.onprogress = event => {
      if (event.lengthComputable) onProgress?.(event.loaded, event.total)
    }
    xhr.onerror = () => reject(Object.assign(new Error('网络连接中断'), { status: 0 }))
    xhr.onabort = () => reject(Object.assign(new Error('上传已暂停'), { aborted: true }))
    xhr.onload = () => {
      const body = (() => {
        try { return JSON.parse(xhr.responseText || '{}') } catch { return {} }
      })()
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body)
        return
      }
      if (xhr.status === 401) {
        setToken(null)
        window.dispatchEvent(new Event('oss:unauthorized'))
      }
      reject(Object.assign(new Error(body.detail || `HTTP ${xhr.status}`), {
        status: xhr.status,
        body,
      }))
    }
    xhr.send(blob)
  })
  return { promise, abort: () => xhr.abort() }
}

export function listVideos({ limit = 12, offset = 0, q = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (q) params.set('q', q)
  return request(`/api/videos?${params}`)
}

export function getVideoSignedLink(code, ttl) {
  const params = new URLSearchParams()
  if (ttl) params.set('ttl', String(ttl))
  const qs = params.toString()
  return request(`/api/videos/${code}/link${qs ? `?${qs}` : ''}`)
}

export function deleteVideo(code) {
  return request(`/api/videos/${code}`, { method: 'DELETE' })
}

export function updateVideo(code, { name, visibility } = {}) {
  return request(`/api/videos/${code}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, visibility }),
  })
}

// --- teams -----------------------------------------------------------------

export function createTeam(name, description) {
  return request('/api/teams', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })
}

export function listTeams() {
  return request('/api/teams')
}

export function getTeam(id) {
  return request(`/api/teams/${id}`)
}

export function addTeamMember(teamId, username) {
  return request(`/api/teams/${teamId}/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  })
}

export function removeTeamMember(teamId, memberId) {
  return request(`/api/teams/${teamId}/members/${memberId}`, { method: 'DELETE' })
}

export function changeTeamMemberRole(teamId, memberId, role) {
  return request(`/api/teams/${teamId}/members/${memberId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })
}

export function deleteTeam(id) {
  return request(`/api/teams/${id}`, { method: 'DELETE' })
}

export function listTeamImages(teamId, { limit = 20, offset = 0, q = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (q) params.set('q', q)
  return request(`/api/teams/${teamId}/images?${params}`)
}

export function listTeamVideos(teamId, { limit = 12, offset = 0, q = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (q) params.set('q', q)
  return request(`/api/teams/${teamId}/videos?${params}`)
}

// --- admin -----------------------------------------------------------------

export function getAdminStats() {
  return request('/api/admin/stats')
}

export function listAdminTeams() {
  return request('/api/admin/teams')
}

export function listUsers() {
  return request('/api/users')
}

export function setUserRole(userId, role) {
  return request(`/api/admin/users/${userId}/role`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })
}

export function resetUserPassword(userId, newPassword) {
  return request(`/api/admin/users/${userId}/password`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_password: newPassword }),
  })
}
