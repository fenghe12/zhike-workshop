const taskService = require('../../services/task-service')
const { formatDateTime, formatFileSize } = require('../../utils/format')
const { getRuntimeConfig } = require('../../config/index')

const STATUS_META = {
  processing: { label: '生成中', className: 'task-running' },
  completed: { label: '已完成', className: 'task-completed' },
  failed: { label: '需要处理', className: 'task-failed' },
  cancelled: { label: '已取消', className: 'task-cancelled' }
}

const STAGE_META = {
  completed: { label: '已完成', className: 'stage-completed', mark: '✓' },
  running: { label: '执行中', className: 'stage-running', mark: '···' },
  failed: { label: '执行失败', className: 'stage-failed', mark: '!' },
  waiting: { label: '等待中', className: 'stage-waiting', mark: '' },
  cancelled: { label: '已取消', className: 'stage-waiting', mark: '—' }
}

Page({
  data: {
    id: '',
    task: null,
    localDataMode: false,
    loading: true
  },

  onLoad(options) {
    this.setData({ id: options.id || '', localDataMode: getRuntimeConfig().localDataMode })
  },

  onShow() {
    if (!this.data.id) return
    this.loadTask().then(() => this.startPolling())
  },

  onHide() {
    this.stopPolling()
  },

  onUnload() {
    this.stopPolling()
  },

  decorateTask(task) {
    if (!task) return null
    const statusMeta = STATUS_META[task.status] || STATUS_META.processing
    const stages = task.stages.map((stage) => {
      const stageMeta = STAGE_META[stage.status] || STAGE_META.waiting
      return Object.assign({}, stage, {
        statusLabel: stageMeta.label,
        statusClass: stageMeta.className,
        statusMark: stageMeta.mark
      })
    })
    const ppt = task.inputs && task.inputs.ppt
    return Object.assign({}, task, {
      statusLabel: statusMeta.label,
      statusClass: statusMeta.className,
      createdLabel: formatDateTime(task.createdAt),
      updatedLabel: formatDateTime(task.updatedAt),
      pptSizeLabel: ppt ? (ppt.sizeLabel || formatFileSize(ppt.size)) : '',
      stages
    })
  },

  loadTask() {
    this.setData({ loading: true })
    return taskService.getTask(this.data.id).then((task) => {
      if (!task) {
        wx.showToast({ title: '任务不存在', icon: 'none' })
        setTimeout(() => wx.navigateBack(), 400)
        return
      }
      wx.setNavigationBarTitle({ title: task.name })
      this.setData({ task: this.decorateTask(task), loading: false })
    }).catch((error) => {
      this.setData({ loading: false })
      wx.showToast({ title: error.message || '任务加载失败', icon: 'none' })
    })
  },

  startPolling() {
    this.stopPolling()
    if (!this.data.task || this.data.task.status !== 'processing') return
    this.pollTimer = setInterval(async () => {
      if (this.pollInFlight) return
      this.pollInFlight = true
      try {
        const updated = await taskService.getTask(this.data.id)
        if (!updated) return
        this.setData({ task: this.decorateTask(updated) })
        if (updated.status !== 'processing') this.stopPolling()
      } catch (error) {
        this.setData({ pollingError: error.message || '任务状态读取失败' })
      } finally {
        this.pollInFlight = false
      }
    }, 1800)
  },

  stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer)
      this.pollTimer = null
    }
  },

  openStage(event) {
    const stage = event.currentTarget.dataset.stage
    wx.navigateTo({ url: `/pages/stage/stage?id=${this.data.id}&stage=${stage}` })
  },

  openAgents() {
    wx.navigateTo({ url: '/pages/agents/agents' })
  },

  retryCurrentStage() {
    const stageIndex = this.data.task.currentStage
    wx.showModal({
      title: `重新执行 S${stageIndex}`,
      content: '当前阶段及后续阶段的进度将重新计算。',
      success: (result) => {
        if (!result.confirm) return
        taskService.retryStage(this.data.id, stageIndex).then((task) => {
          this.setData({ task: this.decorateTask(task) })
          this.startPolling()
        })
      }
    })
  },

  manageTask() {
    const actions = ['修改任务名称']
    if (this.data.task.status === 'processing') actions.push('取消生成任务')
    actions.push('删除任务')
    wx.showActionSheet({
      itemList: actions,
      success: (result) => {
        const action = actions[result.tapIndex]
        if (action === '修改任务名称') this.renameTask()
        if (action === '取消生成任务') this.cancelTask()
        if (action === '删除任务') this.deleteTask()
      }
    })
  },

  renameTask() {
    wx.showModal({
      title: '修改任务名称',
      editable: true,
      placeholderText: this.data.task.name,
      content: this.data.task.name,
      success: (result) => {
        const name = (result.content || '').trim()
        if (!result.confirm || !name) return
        taskService.renameTask(this.data.id, name).then((task) => {
          this.setData({ task: this.decorateTask(task) })
          wx.setNavigationBarTitle({ title: task.name })
        })
      }
    })
  },

  cancelTask() {
    wx.showModal({
      title: '取消生成任务',
      content: '确认停止当前任务吗？已经生成的阶段结果仍会保留。',
      confirmColor: '#A34747',
      success: (result) => {
        if (!result.confirm) return
        taskService.cancelTask(this.data.id).then((task) => {
          this.stopPolling()
          this.setData({ task: this.decorateTask(task) })
        })
      }
    })
  },

  deleteTask() {
    wx.showModal({
      title: '删除任务',
      content: '删除后，该任务记录将无法恢复。',
      confirmText: '删除',
      confirmColor: '#A34747',
      success: (result) => {
        if (!result.confirm) return
        taskService.deleteTask(this.data.id).then(() => {
          wx.showToast({ title: '任务已删除', icon: 'success' })
          setTimeout(() => wx.navigateBack(), 350)
        })
      }
    })
  }
})
