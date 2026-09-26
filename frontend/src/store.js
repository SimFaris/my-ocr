// 全局状态：当前用户、CSRF token、系统状态。
import { reactive } from 'vue'
import { api, setCsrfToken } from './api'

const state = reactive({
  user: null,
  status: null,
  restoring: false,
})

async function restore() {
  if (state.restoring) {
    return state.user !== null
  }
  state.restoring = true
  try {
    const data = await api('GET', '/api/auth/me')
    state.user = data.user
    setCsrfToken(data.csrf)
    return true
  } catch (error) {
    state.user = null
    setCsrfToken('')
    return false
  } finally {
    state.restoring = false
  }
}

async function login(username, password) {
  const data = await api('POST', '/api/auth/login', {
    json: { username, password },
  })
  state.user = data.user
  setCsrfToken(data.csrf)
  return data.user
}

async function logout() {
  try {
    await api('POST', '/api/auth/logout')
  } catch (error) {
    // 会话可能已过期，忽略失败
  }
  state.user = null
  setCsrfToken('')
}

async function loadStatus() {
  state.status = await api('GET', '/api/system/status')
  return state.status
}

export default { state, restore, login, logout, loadStatus }