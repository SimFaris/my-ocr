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
      <nav class="nav">
        <router-link to="/workbench">工作台</router-link>
        <router-link to="/camera">拍照</router-link>
        <router-link to="/jobs">任务列表</router-link>
        <router-link to="/search">检索</router-link>
        <router-link v-if="user && user.role === 'admin'" to="/admin">管理</router-link>
        <router-link to="/status">系统状态</router-link>
      </nav>
      <div class="spacer"></div>
      <span class="who">
        {{ user.display_name || user.username }}（{{ user.role === 'admin' ? '管理员' : '普通用户' }}）
      </span>
      <router-link class="link" to="/account">修改密码</router-link>
      <button class="link" type="button" @click="onLogout">退出登录</button>
    </header>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>