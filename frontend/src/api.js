const TOKEN_KEY = 'oss_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

function expireCurrentToken(requestToken) {
  // A response can arrive after the user has logged out and authenticated as
  // somebody else. Only the credential that actually produced this 401 may
  // invalidate the current browser session.
  if (!requestToken || getToken() !== requestToken) return false
  setToken(null)
  window.dispatchEvent(new Event('oss:unauthorized'))
  return true
}

export function formatApiErrorDetail(detail, status) {
  if (typeof detail === 'string' && detail.trim()) {
    const localized = {
      'user storage quota exceeded': '用户累计存储额度不足',
      'team storage quota exceeded': '团队累计存储额度不足',
      'insufficient storage space': '服务器可用存储空间不足',
    }
    return localized[detail.trim()] || detail
  }
  if (Array.isArray(detail)) {
    const messages = detail.map(item => {
      if (typeof item === 'string') return item
      if (!item || typeof item !== 'object') return ''
      const location = Array.isArray(item.loc)
        ? item.loc.filter(part => !['body', 'query', 'path'].includes(String(part))).join('.')
        : ''
      const message = item.msg || item.message || ''
      return [location, message].filter(Boolean).join('：')
    }).filter(Boolean)
    if (messages.length) return messages.join('；')
  }
  if (detail && typeof detail === 'object') {
    const message = detail.message || detail.msg
    if (message) return String(message)
  }
  return `HTTP ${status}`
}

export async function request(path, options = {}) {
  const { suppressUnauthorized = false, ...fetchOptions } = options
  const headers = { ...(fetchOptions.headers || {}) }
  const storedToken = getToken()
  if (storedToken && !headers.Authorization) headers.Authorization = `Bearer ${storedToken}`
  const requestToken = typeof headers.Authorization === 'string' && headers.Authorization.startsWith('Bearer ')
    ? headers.Authorization.slice(7)
    : null

  const resp = await fetch(path, { ...fetchOptions, headers })
  if (resp.status === 401 && !path.startsWith('/api/auth/') && !suppressUnauthorized) {
    expireCurrentToken(requestToken)
    throw new Error('登录已过期，请重新登录')
  }
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    const error = new Error(formatApiErrorDetail(body.detail, resp.status))
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

export function register(username, password, inviteCode = '') {
  return request('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username,
      password,
      ...(inviteCode ? { invite_code: inviteCode } : {}),
    }),
  })
}

export function fetchPublicConfig({ signal } = {}) {
  return request('/api/auth/config', { suppressUnauthorized: true, signal })
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

export function getVideoUpload(uploadId, { token, suppressUnauthorized = false } = {}) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  return request(`/api/video-uploads/${uploadId}`, { headers, suppressUnauthorized })
}

export function listVideoUploads({ token, suppressUnauthorized = false } = {}) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  return request('/api/video-uploads', { headers, suppressUnauthorized })
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

export function completeVideoUpload(uploadId, { token, suppressUnauthorized = false } = {}) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  return request(`/api/video-uploads/${uploadId}/complete`, {
    method: 'POST',
    headers,
    suppressUnauthorized,
  })
}

export function uploadVideoPart(uploadId, partNumber, blob, {
  start,
  total,
  sha256,
  onProgress,
} = {}) {
  const xhr = new XMLHttpRequest()
  const requestToken = getToken()
  const promise = new Promise((resolve, reject) => {
    xhr.open('PUT', `/api/video-uploads/${uploadId}/parts/${partNumber}`)
    if (requestToken) xhr.setRequestHeader('Authorization', `Bearer ${requestToken}`)
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
        expireCurrentToken(requestToken)
      }
      reject(Object.assign(new Error(formatApiErrorDetail(body.detail, xhr.status)), {
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

// --- unified media library and groups ------------------------------------

function mediaQuery({ teamId, groupId, kind = 'all', q = '', limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams({
    kind,
    limit: String(limit),
    offset: String(offset),
  })
  if (teamId !== null && teamId !== undefined) params.set('team_id', String(teamId))
  if (groupId !== null && groupId !== undefined) params.set('group_id', String(groupId))
  if (q) params.set('q', q)
  return params
}

export function getLibraryStats() {
  return request('/api/library/stats')
}

export function listMedia(options = {}) {
  return request(`/api/media?${mediaQuery(options)}`)
}

export function listMediaGroups({ teamId, q = '', limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (teamId !== null && teamId !== undefined) params.set('team_id', String(teamId))
  if (q) params.set('q', q)
  return request(`/api/media-groups?${params}`)
}

export function createMediaGroup({ name, description = '', color = '#2563eb', sortOrder = 0, teamId = null, codes = [] }) {
  return request('/api/media-groups', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      description,
      color,
      sort_order: sortOrder,
      team_id: teamId,
      ...(codes.length ? { codes } : {}),
    }),
  })
}

export function getMediaGroup(groupId) {
  return request(`/api/media-groups/${groupId}`)
}

export function updateMediaGroup(groupId, { name, description, color, sortOrder } = {}) {
  const payload = {}
  if (name !== undefined) payload.name = name
  if (description !== undefined) payload.description = description
  if (color !== undefined) payload.color = color
  if (sortOrder !== undefined) payload.sort_order = sortOrder
  return request(`/api/media-groups/${groupId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteMediaGroup(groupId) {
  return request(`/api/media-groups/${groupId}`, { method: 'DELETE' })
}

export function listMediaGroupItems(groupId, { kind = 'all', q = '', limit = 20, offset = 0 } = {}) {
  const params = mediaQuery({ kind, q, limit, offset })
  return request(`/api/media-groups/${groupId}/items?${params}`)
}

export function addMediaGroupItems(groupId, codes) {
  return request(`/api/media-groups/${groupId}/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ codes }),
  })
}

export function removeMediaGroupItem(groupId, code) {
  return request(`/api/media-groups/${groupId}/items/${encodeURIComponent(code)}`, { method: 'DELETE' })
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

export function createUser(username, password, role = 'user') {
  return request('/api/admin/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, role }),
  })
}

export function deleteUser(userId) {
  return request(`/api/admin/users/${userId}`, { method: 'DELETE' })
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
