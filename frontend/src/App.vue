<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import store from './store'

const router = useRouter()
const user = computed(() => store.state.user)

async function onLogout() {
  await store.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="layout">
    <header v-if="user" class="topbar">
      <div class="brand">局域网离线 OCR</div>
      <div class="spacer"></div>
      <span class="who">
        {{ user.display_name || user.username }}（{{ user.role === 'admin' ? '管理员' : '普通用户' }}）
      </span>
      <button class="link" type="button" @click="onLogout">退出登录</button>
    </header>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>