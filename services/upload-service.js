const api = require('./api-client')

function upload(file, kind) {
  const path = file.path || file.tempFilePath
  if (!path) return Promise.reject(new Error('未选择上传文件'))
  return new Promise((resolve, reject) => {
    wx.getFileSystemManager().readFile({
      filePath: path,
      encoding: 'base64',
      success: result => api.post('/v1/uploads', {
        filename: file.name || path.split('/').pop(),
        kind,
        contentBase64: result.data
      }).then(resolve, reject),
      fail: () => reject(new Error('无法读取上传文件'))
    })
  })
}

module.exports = { upload }
