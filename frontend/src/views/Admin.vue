<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import store from '../store'

const me = computed(() => store.state.user)
const users = ref([])
const settings = ref(null)
const draft = ref({})
const newUser = ref({ username: '', password: '', display_name: '', role: 'user' })
const createdInfo = ref('')
const cleanupResult = ref(null)
const error = ref('')
const message = ref('')
const busy = ref(false)

async function loadUsers() {
  users.value = (await api('GET', '/api/users')).items
}

async function loadSettings() {
  settings.value = await api('GET', '/api/settings')
  draft.value = Object.assign({}, settings.value.values)
}

onMounted(async () => {
  try {
    await loadUsers()
    await loadSettings()
  } catch (err) {
    error.value = err.message
  }
})

async function run(action, okMessage) {
  busy.value = true
  error.value = ''
  try {
    await action()
    message.value = okMessage || '操作完成'
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

function createUser() {
  createdInfo.value = ''
  run(async () => {
    const data = await api('POST', '/api/users', { json: newUser.value })
    if (data.initial_password) {
      createdInfo.value = '用户 ' + data.user.username + ' 的初始密码：' + data.initial_password + '（请立即转告本人并让其修改）'
    }
    newUser.value = { username: '', password: '', display_name: '', role: 'user' }
    await loadUsers()
  }, '用户已创建')
}

function toggleActive(user) {
  run(async () => {
    await api('PATCH', '/api/users/' + user.id, { json: { is_active: !user.is_active } })
    await loadUsers()
  }, '用户状态已更新')
}

function changeRole(user) {
  const next = user.role === 'admin' ? 'user' : 'admin'
  run(async () => {
    await api('PATCH', '/api/users/' + user.id, { json: { role: next } })
    await loadUsers()
  }, '角色已调整为' + (next === 'admin' ? '管理员' : '普通用户'))
}

function resetPassword(user) {
  if (!window.confirm('确定重置用户「' + user.username + '」的密码吗？' +
    '系统会生成一个随机密码，只显示这一次，请及时抄下来交给本人。')) return
  run(async () => {
    const data = await api('PATCH', '/api/users/' + user.id, { json: { reset_password: true } })
    createdInfo.value = '用户 ' + user.username + ' 的新密码：' + data.new_password +
      '（只显示这一次，请立即抄下来；对方登录后可用「修改密码」改成自己的密码）'
    await loadUsers()
  }, '密码已重置')
}

function saveSettings() {
  run(async () => {
    settings.value = await api('PUT', '/api/settings', { json: { values: draft.value } })
    draft.value = Object.assign({}, settings.value.values)
  }, '设置已保存并立即生效')
}

function runCleanup() {
  run(async () => {
    cleanupResult.value = (await api('POST', '/api/maintenance/cleanup')).result
  }, '清理已执行')
}
</script>

<template>
  <div>
    <div class="card">
      <h2>用户管理</h2>
      <p class="hint">
        普通用户只能看到自己的任务；管理员可以查看全部任务、管理用户与系统设置。
      </p>

      <table class="table">
        <thead>
          <tr><th>用户名</th><th>显示名</th><th>角色</th><th>状态</th><th>最近登录</th><th style="width: 300px">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.username }}</td>
            <td>{{ user.display_name }}</td>
            <td>
              <span class="badge" :class="user.role === 'admin' ? 'warn' : ''">
                {{ user.role === 'admin' ? '管理员' : '普通用户' }}
              </span>
            </td>
            <td>
              <span class="badge" :class="user.is_active ? 'up' : 'down'">
                {{ user.is_active ? '启用' : '停用' }}
              </span>
            </td>
            <td class="hint">{{ user.last_login_at || '从未登录' }}</td>
            <td>
              <div class="actions-inline">
                <button class="btn-mini" type="button" :disabled="busy" @click="changeRole(user)">
                  {{ user.role === 'admin' ? '降为普通用户' : '设为管理员' }}
                </button>
                <button
                  class="btn-mini warn"
                  type="button"
                  :disabled="busy"
                  @click="toggleActive(user)"
                >
                  {{ user.is_active ? '停用' : '启用' }}
                </button>
                <button
                  v-if="me && user.id !== me.id"
                  class="btn-mini"
                  type="button"
                  :disabled="busy"
                  @click="resetPassword(user)"
                >重置密码</button>
                <router-link v-else class="btn-mini" to="/account">改自己的密码</router-link>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <h3 class="sub" style="margin-top: 18px">新建用户</h3>
      <div class="option-row">
        <label>用户名<input v-model="newUser.username" class="title-input" placeholder="3-32 位字母数字" /></label>
        <label>显示名<input v-model="newUser.display_name" class="title-input" placeholder="选填" /></label>
        <label>密码<input v-model="newUser.password" class="title-input" placeholder="留空则自动生成" /></label>
        <label>
          角色
          <select v-model="newUser.role">
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
        </label>
        <label>&nbsp;<button type="button" :disabled="busy" @click="createUser">创建用户</button></label>
      </div>
    </div>

    <div v-if="settings" class="card">
      <h2>系统设置</h2>
      <p class="hint">
        这里的修改立即生效并持久化，不需要重启服务；其余配置（端口、Umi-OCR 路径等）请改
        config.json 后重启。当前配置文件：{{ settings.config_file }}
      </p>
      <div class="option-row">
        <label>结果保留天数<input v-model.number="draft.retention_days" type="number" min="0" /></label>
        <label>磁盘告警水位 (GB)<input v-model.number="draft.disk_min_free_gb" type="number" min="0" /></label>
        <label>单文件上传上限 (MB)<input v-model.number="draft.upload_max_mb" type="number" min="1" /></label>
        <label>
          识别工作线程
          <select v-model.number="draft.ocr_workers">
            <option v-for="n in 8" :key="n" :value="n">{{ n }}</option>
          </select>
        </label>
        <label>
          日志级别
          <select v-model="draft.log_level">
            <option v-for="level in settings.log_levels" :key="level" :value="level">{{ level }}</option>
          </select>
        </label>
        <label>&nbsp;<button type="button" :disabled="busy" @click="saveSettings">保存设置</button></label>
      </div>
      <p class="hint">
        保留天数为 0 表示不自动清理；修改线程数会重启识别线程（正在识别的任务项会在重启后自动重新排队）。
      </p>
    </div>

    <div class="card">
      <h2>维护</h2>
      <p class="hint">手动执行一次保留策略：删除超过保留期的任务及其文件，并清理无主目录。</p>
      <button class="ghost" type="button" :disabled="busy" @click="runCleanup">立即清理</button>
      <pre v-if="cleanupResult" class="result">{{ JSON.stringify(cleanupResult, null, 2) }}</pre>
    </div>

    <div class="card">
      <p v-if="error" class="error">{{ error }}</p>
      <p v-else-if="message" class="ok">{{ message }}</p>
      <p v-if="createdInfo" class="ok">{{ createdInfo }}</p>
    </div>
  </div>
</template>