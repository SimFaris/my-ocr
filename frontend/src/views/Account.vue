<script setup>
import { ref } from 'vue'
import { api } from '../api'

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const message = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  message.value = ''
  if (newPassword.value.length < 8) {
    error.value = '新密码至少 8 位'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = '两次输入的新密码不一致'
    return
  }
  busy.value = true
  try {
    await api('POST', '/api/auth/password', {
      json: { old_password: oldPassword.value, new_password: newPassword.value },
    })
    message.value = '密码已修改。下次登录请使用新密码；首次部署的初始密码文件已自动删除。'
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="card login" style="margin-top: 4vh">
    <h1>修改密码</h1>
    <p class="hint">首次登录后请立即修改初始密码。</p>

    <label>
      当前密码
      <input v-model="oldPassword" type="password" autocomplete="current-password" />
    </label>
    <label>
      新密码（至少 8 位）
      <input v-model="newPassword" type="password" autocomplete="new-password" />
    </label>
    <label>
      确认新密码
      <input v-model="confirmPassword" type="password" autocomplete="new-password" />
    </label>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="message" class="ok">{{ message }}</p>

    <p style="margin-top: 18px">
      <button type="button" :disabled="busy" @click="submit">{{ busy ? '提交中…' : '保存新密码' }}</button>
    </p>
    <p class="hint">
      忘记密码时无法自助找回（本系统离线运行、不依赖邮箱）。请联系服务管理员，在服务机上执行
      <code>python tools\reset_admin.py --username 用户名</code> 重置。
    </p>
  </div>
</template>