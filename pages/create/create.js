const taskService = require('../../services/task-service')
const { formatFileSize } = require('../../utils/format')

function initialLanguages() {
  return [
    { name: '中文', code: 'ZH', selected: true },
    { name: '英语', code: 'EN', selected: true },
    { name: '日语', code: 'JA', selected: true },
    { name: '韩语', code: 'KO', selected: true },
    { name: '德语', code: 'DE', selected: true },
    { name: '法语', code: 'FR', selected: true }
  ]
}

Page({
  data: {
    modes: [
      {
        key: 'upload',
        number: '01',
        title: '上传已有 PPT',
        detail: '自动解析课件页面，提取标题、要点、讲稿和页面布局信息。'
      },
      {
        key: 'topic',
        number: '02',
        title: '输入课程主题',
        detail: '自动生成课程大纲、逐页教学内容、讲稿文本和配套 PPT。'
      }
    ],
    form: {
      name: '人工智能概述多语种课程',
      mode: 'upload',
      ppt: {
        name: 'ch1 人工智能概述-英文.pptx',
        size: 180476226,
        sizeLabel: '172.1 MB',
        path: ''
      },
      topic: '人工智能概述：人工智能的起源与概述、历史与趋势、系统技术架构、机遇与挑战及扩展讨论。'
    },
    languages: initialLanguages(),
    stages: [
      { code: 'S1', title: '课件结构化' },
      { code: 'S2', title: '多语种翻译与校验' },
      { code: 'S3', title: '语音合成' },
      { code: 'S4', title: '数字人生成' },
      { code: 'S5', title: '视频合成' }
    ],
    submitting: false
  },

  onLoad(options) {
    if (options && options.mode === 'topic') {
      this.setData({ 'form.mode': 'topic' })
    }
  },

  onNameInput(event) {
    this.setData({ 'form.name': event.detail.value })
  },

  onTopicInput(event) {
    this.setData({ 'form.topic': event.detail.value })
  },

  selectMode(event) {
    this.setData({ 'form.mode': event.currentTarget.dataset.mode })
  },

  choosePpt() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['ppt', 'pptx'],
      success: (result) => {
        const file = result.tempFiles[0]
        this.setData({
          'form.ppt': {
            name: file.name,
            size: file.size,
            sizeLabel: formatFileSize(file.size),
            path: file.path
          }
        })
      },
      fail: (error) => {
        if (!String(error.errMsg || '').includes('cancel')) {
          wx.showToast({ title: '无法读取 PPT 文件', icon: 'none' })
        }
      }
    })
  },

  removePpt() {
    this.setData({ 'form.ppt': null })
  },

  toggleLanguage(event) {
    const index = Number(event.currentTarget.dataset.index)
    const languages = this.data.languages.slice()
    languages[index] = Object.assign({}, languages[index], { selected: !languages[index].selected })
    this.setData({ languages })
  },

  validate() {
    const form = this.data.form
    const selectedLanguages = this.data.languages.filter((item) => item.selected)
    if (!form.name.trim()) return '请输入任务名称'
    if (!selectedLanguages.length) return '请至少选择一种输出语言'
    if (form.mode === 'upload' && !form.ppt) return '请上传 PPT 课件'
    if (form.mode === 'topic' && !form.topic.trim()) return '请输入课程主题'
    return ''
  },

  submitTask() {
    const errorMessage = this.validate()
    if (errorMessage) {
      wx.showToast({ title: errorMessage, icon: 'none' })
      return
    }
    const targetLanguages = this.data.languages.filter((item) => item.selected).map((item) => item.name)
    const payload = {
      name: this.data.form.name.trim(),
      mode: this.data.form.mode,
      targetLanguages,
      inputs: {
        ppt: this.data.form.mode === 'upload' ? this.data.form.ppt : null,
        topic: this.data.form.mode === 'topic' ? this.data.form.topic.trim() : ''
      }
    }

    this.setData({ submitting: true })
    const prepare = payload.mode === 'upload'
      ? require('../../services/upload-service').upload(payload.inputs.ppt, 'ppt').then(asset => {
        payload.inputs.ppt = asset
      })
      : Promise.resolve()
    prepare.then(() => taskService.createTask(payload)).then((task) => {
      this.setData({ submitting: false })
      wx.navigateTo({ url: `/pages/task/task?id=${task.id}` })
      this.setData({
        form: { name: '', mode: 'upload', ppt: null, topic: '' },
        languages: initialLanguages()
      })
    }).catch((error) => {
      this.setData({ submitting: false })
      wx.showToast({ title: error.message || '任务创建失败', icon: 'none' })
    })
  }
})
