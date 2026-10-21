const taskService = require('./services/task-service')
const { getRuntimeConfig } = require('./config/index')

App({
  globalData: {
    appName: '智课工坊',
    version: '1.0.0',
    localDataMode: false
  },

  onLaunch() {
    taskService.initialize()
    this.globalData.localDataMode = getRuntimeConfig().localDataMode
  }
})
