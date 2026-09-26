// 统一的接口调用封装：同源 Cookie 会话 + CSRF 头 + 结构化错误。
let csrfToken = ''

export function setCsrfToken(token) {
  csrfToken = token || ''
}

export function getCsrfToken() {
  return csrfToken
}

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

const UNSAFE_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']

export async function api(method, path, options) {
  const settings = options || {}
  const headers = Object.assign({}, settings.headers)
  const init = { method, headers, credentials: 'same-origin' }

  if (settings.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(settings.json)
  }
  if (UNSAFE_METHODS.indexOf(method) >= 0 && csrfToken) {
    headers['X-CSRF-Token'] = csrfToken
  }

  const response = await fetch(path, init)
  if (settings.raw) {
    return response
  }

  let payload = null
  try {
    payload = await response.json()
  } catch (error) {
    payload = null
  }

  if (!response.ok || !payload || payload.ok === false) {
    const detail = (payload && payload.error) || {}
    throw new ApiError(
      detail.code || 'http_' + response.status,
      detail.message || '请求失败（HTTP ' + response.status + '）',
      response.status,
    )
  }
  return payload.data
}