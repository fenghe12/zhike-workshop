const { getRuntimeConfig } = require('../config/index')

function request(options) {
  const config = getRuntimeConfig()
  const token = wx.getStorageSync('zhike_access_token') || ''

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${config.baseUrl}${options.path}`,
      method: options.method || 'GET',
      data: options.data || {},
      timeout: config.requestTimeout,
      header: Object.assign(
        {
          'content-type': 'application/json',
          authorization: token ? `Bearer ${token}` : ''
        },
        options.header || {}
      ),
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data)
          return
        }
        const error = new Error((response.data && response.data.message) || `请求失败：${response.statusCode}`)
        error.statusCode = response.statusCode
        error.data = response.data
        reject(error)
      },
      fail(error) {
        reject(error)
      }
    })
  })
}

module.exports = {
  get(path) {
    return request({ path, method: 'GET' })
  },
  post(path, data) {
    return request({ path, method: 'POST', data })
  },
  put(path, data) {
    return request({ path, method: 'PUT', data })
  },
  request
}
