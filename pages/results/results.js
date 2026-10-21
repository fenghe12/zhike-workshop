const taskService = require('../../services/task-service')
const { formatDateTime } = require('../../utils/format')

Page({
  data: {
    tasks: [],
    loading: true
  },

  onShow() {
    this.loadResults()
  },

  onPullDownRefresh() {
    this.loadResults().finally(() => wx.stopPullDownRefresh())
  },

  loadResults() {
    this.setData({ loading: true })
    return taskService.listTasks('completed').then((tasks) => {
      const decorated = tasks.map((task) => Object.assign({}, task, {
        completedLabel: formatDateTime(task.updatedAt),
        video: task.outputs.s5,
        primaryLanguage: task.targetLanguages[0],
        languageCount: task.targetLanguages.length
      }))
      this.setData({ tasks: decorated, loading: false })
    }).catch((error) => {
      this.setData({ loading: false })
      wx.showToast({ title: error.message || '结果加载失败', icon: 'none' })
    })
  },

  openTask(event) {
    wx.navigateTo({ url: `/pages/task/task?id=${event.currentTarget.dataset.id}` })
  },

  openResult(event) {
    wx.navigateTo({ url: `/pages/stage/stage?id=${event.currentTarget.dataset.id}&stage=5` })
  },

  exportSubtitle(event) {
    const task = this.data.tasks.find((item) => item.id === event.currentTarget.dataset.id)
    if (!task) return
    if (task.outputs.s5.subtitleAsset) {
      wx.getFileSystemManager().readFile({
        filePath: task.outputs.s5.subtitleAsset,
        encoding: 'utf8',
        success: (result) => this.writeSubtitleFile(task, result.data),
        fail: () => wx.showToast({ title: '字幕文件读取失败', icon: 'none' })
      })
      return
    }
    const subtitles = task.outputs.s5.subtitlePreview || []
    const content = subtitles.map((item) => `${item.index}\n${item.time.replace(' → ', ' --> ')}\n${item.text}\n`).join('\n')
    this.writeSubtitleFile(task, content)
  },

  writeSubtitleFile(task, content) {
    const fileName = `${task.name}.srt`
    const filePath = `${wx.env.USER_DATA_PATH}/${fileName}`
    wx.getFileSystemManager().writeFile({
      filePath,
      data: content,
      encoding: 'utf8',
      success: () => {
        if (typeof wx.shareFileMessage === 'function') {
          wx.shareFileMessage({ filePath, fileName, fail: () => wx.showToast({ title: 'SRT 文件已生成', icon: 'none' }) })
        } else {
          wx.showToast({ title: 'SRT 文件已生成', icon: 'success' })
        }
      },
      fail: () => wx.showToast({ title: 'SRT 生成失败', icon: 'none' })
    })
  }
})
