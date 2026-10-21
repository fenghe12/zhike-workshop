const { getRuntimeConfig, saveRuntimeConfig } = require('../../config/index')
const taskService = require('../../services/task-service')
const api = require('../../services/api-client')

Page({
  data: {
    user: {},
    config: {},
    connectionState: '未检测',
    testing: false
  },

  onShow() {
    const storedUser = wx.getStorageSync('zhike_user') || { name: '课程管理员', account: 'teacher@hit.edu.cn', institution: '哈尔滨工业大学' }
    this.setData({
      user: Object.assign({}, storedUser, { avatarInitial: String(storedUser.name || '智').slice(0, 1) }),
      config: getRuntimeConfig(),
      connectionState: '运行正常'
    })
  },

  onBaseUrlInput(event) {
    this.setData({ 'config.baseUrl': event.detail.value })
  },

  onMaxRetriesInput(event) {
    this.setData({ 'config.maxTranslationRetries': Number(event.detail.value) || 3 })
  },

  onSemanticInput(event) {
    this.setData({ 'config.semanticThreshold': Number(event.detail.value) || 0.85 })
  },

  onTerminologyInput(event) {
    this.setData({ 'config.terminologyThreshold': Number(event.detail.value) || 0.9 })
  },

  saveConfig() {
    const baseUrl = String(this.data.config.baseUrl || '').trim().replace(/\/$/, '')
    if (!this.data.config.localDataMode && !/^https?:\/\//.test(baseUrl)) {
      wx.showToast({ title: '请输入有效的后端地址', icon: 'none' })
      return
    }
    const config = saveRuntimeConfig(Object.assign({}, this.data.config, { baseUrl }))
    this.setData({ config })
    wx.showToast({ title: '设置已保存', icon: 'success' })
  },

  testConnection() {
    if (this.data.config.localDataMode) {
      this.setData({ connectionState: '运行正常' })
      wx.showToast({ title: '任务数据可用', icon: 'success' })
      return
    }
    this.saveConfig()
    this.setData({ testing: true, connectionState: '检测中' })
    api.get('/v1/health').then(() => {
      this.setData({ testing: false, connectionState: '连接正常' })
      wx.showToast({ title: '后端连接正常', icon: 'success' })
    }).catch(() => {
      this.setData({ testing: false, connectionState: '连接失败' })
      wx.showToast({ title: '无法连接后端', icon: 'none' })
    })
  },

  logout() {
    wx.showModal({
      title: '退出登录',
      content: '确认退出当前账号吗？',
      success: (result) => {
        if (!result.confirm) return
        wx.removeStorageSync('zhike_user')
        wx.removeStorageSync('zhike_access_token')
        wx.reLaunch({ url: '/pages/login/login' })
      }
    })
  }
})
