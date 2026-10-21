function pad(value) {
  return String(value).padStart(2, '0')
}

function formatDateTime(timestamp) {
  const date = new Date(timestamp)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function formatDuration(seconds) {
  const value = Number(seconds) || 0
  const minutes = Math.floor(value / 60)
  const rest = Math.floor(value % 60)
  return `${pad(minutes)}:${pad(rest)}`
}

function formatFileSize(bytes) {
  const value = Number(bytes) || 0
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function createId(prefix) {
  return `${prefix || 'id'}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`
}

module.exports = {
  formatDateTime,
  formatDuration,
  formatFileSize,
  createId
}
