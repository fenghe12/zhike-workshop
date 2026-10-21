const api = require('./api-client')

function saveSession(result) {
  if (!result || !result.accessToken || !result.user) {
    throw new Error('登录服务未返回有效会话')
  }
  const user = result.user
  wx.setStorageSync('zhike_access_token', result.accessToken)
  wx.setStorageSync('zhike_user', {
    name: user.displayName || user.name || '',
    account: user.phone || user.account || '',
    institution: user.institution || ''
  })
  return user
}
function login(payload) { return api.post('/v1/auth/login', payload).then(saveSession) }
function register(payload) { return api.post('/v1/auth/register', payload).then(saveSession) }
module.exports = { login, register }
