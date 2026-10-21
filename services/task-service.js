const api = require('./api-client')

// Task state comes exclusively from the backend execution records.
function initialize() {}
function listTasks(filter) {
  const query = filter && filter !== 'all' ? `?status=${encodeURIComponent(filter)}` : ''
  return api.get(`/v1/tasks${query}`)
}
function getTask(id) { return api.get(`/v1/tasks/${encodeURIComponent(id)}`) }
function createTask(payload) { return api.post('/v1/tasks', payload) }
function retryStage(id, stage) { return api.post(`/v1/tasks/${encodeURIComponent(id)}/stages/${stage}/retry`, {}) }
function renameTask(id, name) { return api.put(`/v1/tasks/${encodeURIComponent(id)}`, { name }) }
function cancelTask(id) { return api.post(`/v1/tasks/${encodeURIComponent(id)}/cancel`, {}) }
function deleteTask(id) { return api.request({ path: `/v1/tasks/${encodeURIComponent(id)}`, method: 'DELETE' }) }
function updateAssets(id, patch) { return api.put(`/v1/tasks/${encodeURIComponent(id)}/assets`, patch) }
module.exports = { initialize, listTasks, getTask, createTask, retryStage, renameTask, cancelTask, deleteTask, updateAssets }
