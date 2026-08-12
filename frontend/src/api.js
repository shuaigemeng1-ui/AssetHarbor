const TOKEN_KEY = 'oss_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const resp = await fetch(path, { ...options, headers })
  if (resp.status === 401 && !path.startsWith('/api/auth/')) {
    setToken(null)
    window.dispatchEvent(new Event('oss:unauthorized'))
    throw new Error('登录已过期，请重新登录')
  }
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) throw new Error(body.detail || `HTTP ${resp.status}`)
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

export function listImages({ limit = 100, q = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
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

export function listTeamImages(teamId, { limit = 100, q = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (q) params.set('q', q)
  return request(`/api/teams/${teamId}/images?${params}`)
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
