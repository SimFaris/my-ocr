<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import store from '../store'

const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

const route = useRoute()
const router = useRouter()

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
    <p class="hint">
      请使用分配的账号登录。初始管理员账号见服务端 data/initial_admin_password.txt。
    </p>

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