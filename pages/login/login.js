const authService = require('../../services/auth-service')

Page({
  data: {
    account: 'teacher@hit.edu.cn',
    password: '123456',
    passwordVisible: false,
    submitting: false
  },

  onAccountInput(event) {
    this.setData({ account: event.detail.value })
  },

  onPasswordInput(event) {
    this.setData({ password: event.detail.value })
  },

  togglePassword() {
    this.setData({ passwordVisible: !this.data.passwordVisible })
  },

  submitLogin() {
    if (!this.data.account.trim() || !this.data.password.trim()) {
      wx.showToast({ title: '请输入账号和密码', icon: 'none' })
      return
    }
    this.setData({ submitting: true })
    authService.login({ account: this.data.account.trim(), password: this.data.password }).then(() => {
      this.setData({ submitting: false })
      wx.switchTab({ url: '/pages/home/home' })
    }).catch((error) => {
      this.setData({ submitting: false })
      wx.showToast({ title: error.message || '登录失败', icon: 'none' })
    })
  },

  openRegister() {
    wx.navigateTo({ url: '/pages/register/register' })
  }
})
