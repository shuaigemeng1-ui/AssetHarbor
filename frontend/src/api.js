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

export function uploadFile(file, { name = '', visibility = 'public' } = {}) {
  const fd = new FormData()
  fd.append('file', file, file.name)
  fd.append('visibility', visibility)
  if (name) fd.append('name', name)
  return request('/api/upload', { method: 'POST', body: fd })
}

export function listImages({ limit = 100, q = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (q) params.set('q', q)
  return request(`/api/images?${params}`)
}
