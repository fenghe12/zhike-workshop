const DEFAULT_CONFIG = {
  localDataMode: false,
  baseUrl: 'http://127.0.0.1:8080',
  requestTimeout: 30000,
  maxTranslationRetries: 3,
  semanticThreshold: 0.85,
  terminologyThreshold: 0.9
}

function getRuntimeConfig() {
  const saved = wx.getStorageSync('zhike_runtime_config') || {}
  return Object.assign({}, DEFAULT_CONFIG, saved, { localDataMode: false })
}

function saveRuntimeConfig(nextConfig) {
  const merged = Object.assign({}, getRuntimeConfig(), nextConfig)
  wx.setStorageSync('zhike_runtime_config', merged)
  return merged
}

module.exports = {
  DEFAULT_CONFIG,
  getRuntimeConfig,
  saveRuntimeConfig
}
