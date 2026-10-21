const taskService = require('../../services/task-service')
const { formatFileSize } = require('../../utils/format')
const { getRuntimeConfig } = require('../../config/index')

Page({
  data: {
    id: '',
    stageIndex: 1,
    task: null,
    stage: null,
    output: null,
    localDataMode: true,
    loading: true,
    activeLanguageIndex: 0,
    activePageIndex: 0,
    showAllPages: false,
    playing: false
  },

  onLoad(options) {
    const stageIndex = Math.max(1, Math.min(5, Number(options.stage) || 1))
    this.setData({
      id: options.id || '',
      stageIndex,
      localDataMode: getRuntimeConfig().localDataMode
    })
  },

  onShow() {
    this.loadStage()
  },

  onUnload() {
    if (this.audioContext) {
      this.audioContext.stop()
      this.audioContext.destroy()
      this.audioContext = null
    }
  },

  loadStage() {
    this.setData({ loading: true })
    return taskService.getTask(this.data.id).then((task) => {
      if (!task) throw new Error('任务不存在')
      const stage = task.stages.find((item) => item.index === this.data.stageIndex)
      let output = (task.outputs || {})[`s${this.data.stageIndex}`] || {}
      if (this.data.stageIndex === 2 && output.languageDetails && output.languageDetails.length) {
        const detail = output.languageDetails[this.data.activeLanguageIndex] || output.languageDetails[0]
        output = Object.assign({}, output, {
          activeLanguage: detail.name,
          metrics: detail.metrics,
          samples: detail.samples
        })
      }
      wx.setNavigationBarTitle({ title: `${stage.code} ${stage.title}` })
      this.setData({ task, stage, output, loading: false })
    }).catch((error) => {
      this.setData({ loading: false })
      wx.showToast({ title: error.message || '阶段数据加载失败', icon: 'none' })
    })
  },

  switchLanguage(event) {
    const activeLanguageIndex = Number(event.currentTarget.dataset.index)
    const detail = this.data.output.languageDetails && this.data.output.languageDetails[activeLanguageIndex]
    if (!detail) {
      this.setData({ activeLanguageIndex })
      return
    }
    this.setData({
      activeLanguageIndex,
      'output.activeLanguage': detail.name,
      'output.metrics': detail.metrics,
      'output.samples': detail.samples
    })
  },

  switchPage(event) {
    this.setData({ activePageIndex: Number(event.currentTarget.dataset.index) })
  },

  toggleAllPages() {
    this.setData({ showAllPages: !this.data.showAllPages })
  },

  chooseReferenceAudio() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['wav', 'mp3', 'm4a', 'aac'],
      success: (result) => {
        const file = result.tempFiles[0]
        const asset = {
          name: file.name,
          size: file.size,
          sizeLabel: formatFileSize(file.size),
          path: file.path
        }
        require('../../services/upload-service').upload(asset, 'audio')
          .then(uploaded => taskService.updateAssets(this.data.id, { referenceAudio: uploaded })).then((task) => {
          this.setData({ task })
          wx.showToast({ title: '参考音频已添加', icon: 'success' })
        }).catch(error => wx.showToast({ title: error.message || '音频上传失败', icon: 'none' }))
      }
    })
  },

  chooseReferenceImage() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: (result) => {
        const file = result.tempFiles[0]
        const nameParts = String(file.tempFilePath).split('/')
        const asset = {
          name: nameParts[nameParts.length - 1] || 'reference_image.jpg',
          size: file.size,
          sizeLabel: formatFileSize(file.size),
          path: file.tempFilePath
        }
        require('../../services/upload-service').upload(asset, 'image')
          .then(uploaded => taskService.updateAssets(this.data.id, { referenceImage: uploaded })).then((task) => {
          this.setData({ task })
          wx.showToast({ title: '参考图片已添加', icon: 'success' })
        }).catch(error => wx.showToast({ title: error.message || '图片上传失败', icon: 'none' }))
      }
    })
  },

  toggleAudio() {
    const audioAsset = this.data.output && this.data.output.audioAsset
    if (!audioAsset) {
      wx.showToast({ title: '未找到音频试听文件', icon: 'none' })
      return
    }
    if (!this.audioContext) {
      this.audioContext = wx.createInnerAudioContext()
      this.audioContext.src = audioAsset
      this.audioContext.onEnded(() => this.setData({ playing: false }))
      this.audioContext.onError(() => {
        this.setData({ playing: false })
        wx.showToast({ title: '音频试听文件读取失败', icon: 'none' })
      })
    }
    if (this.data.playing) {
      this.audioContext.pause()
      this.setData({ playing: false })
      return
    }
    this.audioContext.play()
    this.setData({ playing: true })
  },

  previewVideo() {
    const videoUrl = this.data.output && this.data.output.videoUrl
    if (videoUrl) {
      wx.previewMedia({ sources: [{ url: videoUrl, type: 'video' }] })
      return
    }
    wx.showModal({
      title: '课程视频预览',
      content: '课程视频已保存在后端产物目录，当前页面展示与统一时间轴对应的真实课件画面、数字人和字幕信息。',
      showCancel: false
    })
  },

  exportTextFile(fileName, content) {
    const filePath = `${wx.env.USER_DATA_PATH}/${fileName}`
    const fileSystem = wx.getFileSystemManager()
    fileSystem.writeFile({
      filePath,
      data: content,
      encoding: 'utf8',
      success: () => {
        if (typeof wx.shareFileMessage === 'function') {
          wx.shareFileMessage({
            filePath,
            fileName,
            fail: () => wx.showToast({ title: `文件已生成：${fileName}`, icon: 'none' })
          })
        } else {
          wx.showToast({ title: `文件已生成：${fileName}`, icon: 'none' })
        }
      },
      fail: () => wx.showToast({ title: '文件生成失败', icon: 'none' })
    })
  },

  exportStageData() {
    const fileName = `${this.data.task.id}_S${this.data.stageIndex}.json`
    this.exportTextFile(fileName, JSON.stringify(this.data.output, null, 2))
  },

  downloadOutput(event) {
    const key = event.currentTarget.dataset.key
    if (key === 'subtitle') {
      if (this.data.output.subtitleAsset) {
        wx.getFileSystemManager().readFile({
          filePath: this.data.output.subtitleAsset,
          encoding: 'utf8',
          success: (result) => this.exportTextFile(`${this.data.task.name}.srt`, result.data),
          fail: () => wx.showToast({ title: '字幕文件读取失败', icon: 'none' })
        })
        return
      }
      const subtitles = this.data.output.subtitlePreview || []
      const srt = subtitles.map((item) => `${item.index}\n${item.time.replace(' → ', ' --> ')}\n${item.text}\n`).join('\n')
      this.exportTextFile(`${this.data.task.name}.srt`, srt)
      return
    }
    if (key === 'timeline' || key === 'report') {
      this.exportStageData()
      return
    }
    wx.showModal({
      title: '课程视频下载',
      content: '课程视频文件已由后端生成，下载接口按任务编号返回实际结果文件。',
      showCancel: false
    })
  },

  retryStage() {
    wx.showModal({
      title: `重新执行 ${this.data.stage.code}`,
      content: '该阶段和后续阶段将重新处理。',
      success: (result) => {
        if (!result.confirm) return
        taskService.retryStage(this.data.id, this.data.stageIndex).then(() => {
          wx.showToast({ title: '已重新提交', icon: 'success' })
          this.loadStage()
        })
      }
    })
  },

  goPrevious() {
    if (this.data.stageIndex <= 1) return
    wx.redirectTo({ url: `/pages/stage/stage?id=${this.data.id}&stage=${this.data.stageIndex - 1}` })
  },

  goNext() {
    if (this.data.stageIndex >= 5) {
      wx.switchTab({ url: '/pages/results/results' })
      return
    }
    wx.redirectTo({ url: `/pages/stage/stage?id=${this.data.id}&stage=${this.data.stageIndex + 1}` })
  }
})
