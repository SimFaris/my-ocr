<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import store from '../store'
import { api } from '../api'

const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

const route = useRoute()
const router = useRouter()
const hint = ref(null)

onMounted(async () => {
  try {
    const data = await api('GET', '/api/auth/bootstrap-hint')
    if (data && data.visible) hint.value = data
  } catch (err) {
    // 取不到就不显示提示，不影响登录
  }
})

function fillHint() {
  if (!hint.value) return
  username.value = hint.value.username
  password.value = hint.value.password
}

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await store.login(username.value.trim(), password.value)
    const next = route.query.next
    router.push(typeof next === 'string' && next ? next : '/')
  } catch (exception) {
    error.value = exception.message || '登录失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="card login" @submit.prevent="submit">
    <h1>局域网离线 OCR</h1>
    <div v-if="hint" class="bootstrap-hint">
      <strong>初始登录凭据</strong>
      <p>账号 <code>{{ hint.username }}</code>　密码 <code>{{ hint.password }}</code></p>
      <p class="hint">仅在首次部署、尚未修改密码时显示；改密后自动消失。</p>
      <button class="ghost" type="button" @click="fillHint">填入登录框</button>
    </div>
    <p v-else class="hint">请使用分配的账号登录。初始管理员账号见服务端 data/initial_admin_password.txt。</p>

    <label>
      用户名
      <input v-model="username" autocomplete="username" autocapitalize="off" required />
    </label>

    <label>
      密码
      <input v-model="password" type="password" autocomplete="current-password" required />
    </label>

    <p v-if="error" class="error">{{ error }}</p>

    <p style="margin-top: 18px">
      <button type="submit" :disabled="busy">{{ busy ? '登录中…' : '登录' }}</button>
    </p>
  </form>
</template>