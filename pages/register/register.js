const authService = require('../../services/auth-service')

Page({
  data: {
    form: {
      name: '冯赫',
      institution: '哈尔滨工业大学',
      account: 'teacher@hit.edu.cn',
      password: '123456',
      confirmPassword: '123456'
    },
    agreed: true,
    submitting: false
  },

  onInput(event) {
    const key = event.currentTarget.dataset.key
    const form = Object.assign({}, this.data.form)
    form[key] = event.detail.value
    this.setData({ form })
  },

  toggleAgreement() {
    this.setData({ agreed: !this.data.agreed })
  },

  submitRegister() {
    const form = this.data.form
    if (!form.name.trim() || !form.institution.trim() || !form.account.trim() || !form.password) {
      wx.showToast({ title: '请填写所有必填信息', icon: 'none' })
      return
    }
    if (form.password.length < 6) {
      wx.showToast({ title: '密码至少为 6 位', icon: 'none' })
      return
    }
    if (form.password !== form.confirmPassword) {
      wx.showToast({ title: '两次输入的密码不一致', icon: 'none' })
      return
    }
    if (!this.data.agreed) {
      wx.showToast({ title: '请确认用户协议与隐私说明', icon: 'none' })
      return
    }

    this.setData({ submitting: true })
    authService.register({
      name: form.name,
      account: form.account,
      institution: form.institution,
      password: form.password
    }).then(() => {
      this.setData({ submitting: false })
      wx.showToast({ title: '注册完成', icon: 'success' })
      setTimeout(() => wx.switchTab({ url: '/pages/home/home' }), 350)
    }).catch((error) => {
      this.setData({ submitting: false })
      wx.showToast({ title: error.message || '注册失败', icon: 'none' })
    })
  }
})
