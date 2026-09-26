import { createRouter, createWebHashHistory } from 'vue-router'
import Login from './views/Login.vue'
import Workbench from './views/Workbench.vue'
import Jobs from './views/Jobs.vue'
import JobDetail from './views/JobDetail.vue'
import Dashboard from './views/Dashboard.vue'
import store from './store'

// 使用 hash 路由：服务端不需要为前端路由做任何 URL 重写。
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/workbench' },
    { path: '/workbench', name: 'workbench', component: Workbench, meta: { requiresAuth: true } },
    { path: '/jobs', name: 'jobs', component: Jobs, meta: { requiresAuth: true } },
    { path: '/jobs/:id', name: 'job-detail', component: JobDetail, meta: { requiresAuth: true } },
    { path: '/status', name: 'status', component: Dashboard, meta: { requiresAuth: true } },
    { path: '/login', name: 'login', component: Login },
    { path: '/:pathMatch(.*)*', redirect: '/workbench' },
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
    return { name: 'workbench' }
  }
  return true
})

export default router