export function formatBytes(value = 0) {
  const bytes = Number(value) || 0
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

export function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '计算中'
  if (seconds < 60) return `${Math.ceil(seconds)} 秒`
  if (seconds < 3600) return `${Math.ceil(seconds / 60)} 分钟`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.ceil((seconds % 3600) / 60)
  return `${hours} 小时${minutes ? ` ${minutes} 分钟` : ''}`
}

export function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN')
}
