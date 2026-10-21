const taskService = require('../../services/task-service')
const { formatDateTime } = require('../../utils/format')

const STATUS_META = {
  processing: { label: '生成中', className: 'status-running' },
  completed: { label: '已完成', className: 'status-completed' },
  failed: { label: '需处理', className: 'status-failed' },
  cancelled: { label: '已取消', className: 'status-waiting' },
  waiting: { label: '等待中', className: 'status-waiting' }
}

Page({
  data: {
    user: {},
    activeFilter: 'all',
    filters: [
      { key: 'all', label: '全部' },
      { key: 'processing', label: '生成中' },
      { key: 'completed', label: '已完成' },
      { key: 'failed', label: '需处理' }
    ],
    tasks: [],
    stats: { total: 0, processing: 0, completed: 0, languages: 0 },
    loading: true
  },

  onShow() {
    const storedUser = wx.getStorageSync('zhike_user') || { name: '课程管理员', institution: '高校在线教育中心' }
    const user = Object.assign({}, storedUser, { avatarInitial: String(storedUser.name || '智').slice(0, 1) })
    this.setData({ user })
    this.loadTasks()
  },

  onPullDownRefresh() {
    this.loadTasks().finally(() => wx.stopPullDownRefresh())
  },

  loadTasks() {
    this.setData({ loading: true })
    return taskService.listTasks(this.data.activeFilter).then((tasks) => {
      const decorated = tasks.map((task) => {
        const statusMeta = STATUS_META[task.status] || STATUS_META.waiting
        const activeStage = task.stages.find((stage) => stage.index === task.currentStage) || task.stages[task.stages.length - 1]
        return Object.assign({}, task, {
          statusLabel: statusMeta.label,
          statusClass: statusMeta.className,
          updatedLabel: formatDateTime(task.updatedAt),
          activeStageTitle: activeStage ? `${activeStage.code} ${activeStage.title}` : '等待任务启动',
          languageCount: task.targetLanguages.length
        })
      })
      this.setData({ tasks: decorated, loading: false })
      return taskService.listTasks('all')
    }).then((allTasks) => {
      const languageSet = {}
      allTasks.forEach((task) => task.targetLanguages.forEach((language) => { languageSet[language] = true }))
      this.setData({
        stats: {
          total: allTasks.length,
          processing: allTasks.filter((task) => task.status === 'processing').length,
          completed: allTasks.filter((task) => task.status === 'completed').length,
          languages: Object.keys(languageSet).length
        }
      })
    }).catch((error) => {
      this.setData({ loading: false })
      wx.showToast({ title: error.message || '任务加载失败', icon: 'none' })
    })
  },

  changeFilter(event) {
    this.setData({ activeFilter: event.currentTarget.dataset.key }, () => this.loadTasks())
  },

  openTask(event) {
    wx.navigateTo({ url: `/pages/task/task?id=${event.currentTarget.dataset.id}` })
  },

  createTask() {
    wx.switchTab({ url: '/pages/create/create' })
  },

  openAgents() {
    wx.navigateTo({ url: '/pages/agents/agents' })
  }
})
