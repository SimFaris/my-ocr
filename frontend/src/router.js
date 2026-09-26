import { createRouter, createWebHashHistory } from 'vue-router'
import Login from './views/Login.vue'
import Dashboard from './views/Dashboard.vue'
import store from './store'

// 使用 hash 路由：服务端不需要为前端路由做任何 URL 重写。
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard, meta: { requiresAuth: true } },
    { path: '/login', name: 'login', component: Login },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.requiresAuth && !store.state.user) {
    const restored = await store.restore()
    if (!restored) {
      return { name: 'login', query: { next: to.fullPath } }
    }
  }
  if (to.name === 'login' && store.state.user) {
    return { name: 'dashboard' }
  }
  return true
})

export default router