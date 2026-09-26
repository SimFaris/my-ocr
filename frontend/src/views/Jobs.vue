<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import store from '../store'

const router = useRouter()

const isAdmin = computed(() => !!store.state.user && store.state.user.role === 'admin')
// 管理员默认看全部用户的任务（后端只在 scope=all 且是管理员时才放开）
const scope = ref('all')
const showAll = computed(() => isAdmin.value && scope.value === 'all')

const jobs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const status = ref('')
const error = ref('')
const busyId = ref('')

const STATUS_LABELS = {
  draft: '待提交',
  queued: '排队中',
  running: '识别中',
  done: '已完成',
  partial: '部分完成',
  failed: '失败',
  canceled: '已取消',
}
const STATUS_CLASS = {
  done: 'up',
  failed: 'down',
  running: 'warn',
  queued: 'warn',
  partial: 'warn',
  draft: '',
  canceled: '',
}

function label(value) {
  return STATUS_LABELS[value] || value
}

function badgeClass(value) {
  return STATUS_CLASS[value] || ''
}

async function load() {
  try {
    const query = new URLSearchParams({ page: String(page.value), page_size: String(pageSize) })
    if (status.value) query.set('status', status.value)
    if (showAll.value) query.set('scope', 'all')
    const data = await api('GET', '/api/jobs?' + query.toString())
    jobs.value = data.items
    total.value = data.total
    error.value = ''
  } catch (err) {
    error.value = err.message
  }
}

onMounted(load)

async function act(job, action) {
  if (action === 'delete' && !window.confirm('确定删除任务「' + job.title + '」吗？相关文件会一并删除。')) {
    return
  }
  if (action === 'cancel' && !window.confirm('确定取消任务「' + job.title + '」吗？')) {
    return
  }
  busyId.value = job.id
  try {
    if (action === 'cancel') {
      await api('POST', '/api/jobs/' + job.id + '/cancel')
    } else if (action === 'retry') {
      await api('POST', '/api/jobs/' + job.id + '/retry')
    } else if (action === 'delete') {
      await api('DELETE', '/api/jobs/' + job.id)
    }
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    busyId.value = ''
  }
}

function open(job) {
  router.push({ name: 'job-detail', params: { id: job.id } })
}

const totalPages = () => Math.max(1, Math.ceil(total.value / pageSize))

function go(delta) {
  const next = page.value + delta
  if (next < 1 || next > totalPages()) return
  page.value = next
  load()
}
</script>

<template>
  <div>
    <div class="card">
      <div class="row-between">
        <h2>任务列表</h2>
        <div class="row-between">
          <select v-if="isAdmin" v-model="scope" @change="page = 1; load()">
            <option value="all">全部用户的任务</option>
            <option value="mine">只看我的任务</option>
          </select>
          <select v-model="status" @change="page = 1; load()">
            <option value="">全部状态</option>
            <option value="draft">待提交</option>
            <option value="queued">排队中</option>
            <option value="running">识别中</option>
            <option value="done">已完成</option>
            <option value="partial">部分完成</option>
            <option value="failed">失败</option>
            <option value="canceled">已取消</option>
          </select>
          <button class="ghost" type="button" @click="load">刷新</button>
        </div>
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <table class="table">
        <thead>
          <tr>
            <th style="width: 28%">任务</th>
            <th v-if="showAll">用户</th>
            <th>状态</th>
            <th>进度</th>
            <th>创建时间</th>
            <th v-if="showAll">来源</th>
            <th style="width: 260px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.id">
            <td class="ellipsis">
              <a href="javascript:void(0)" @click="open(job)">{{ job.title }}</a>
              <span v-if="showAll && job.user_id === (store.state.user && store.state.user.id)" class="hint">（我）</span>
            </td>
            <td v-if="showAll">{{ job.user_display_name || job.username || job.user_id }}</td>
            <td><span class="badge" :class="badgeClass(job.status)">{{ label(job.status) }}</span></td>
            <td>
              {{ job.item_done }} / {{ job.item_total }}
              <span v-if="job.item_failed">（失败 {{ job.item_failed }}）</span>
            </td>
            <td class="hint">{{ job.created_at }}</td>
            <td v-if="showAll" class="hint">
              {{ job.client_ip || '（旧数据未记录）' }}
              <span v-if="job.client_host">（{{ job.client_host }}）</span>
            </td>
            <td>
              <div class="actions-inline">
                <button class="btn-mini" type="button" @click="open(job)">查看</button>
                <button
                  v-if="['draft', 'queued', 'running'].indexOf(job.status) >= 0"
                  class="btn-mini warn"
                  type="button"
                  :disabled="busyId === job.id"
                  @click="act(job, 'cancel')"
                >取消</button>
                <button
                  v-if="['failed', 'partial', 'canceled'].indexOf(job.status) >= 0"
                  class="btn-mini"
                  type="button"
                  :disabled="busyId === job.id"
                  @click="act(job, 'retry')"
                >重试失败项</button>
                <button
                  class="btn-mini danger"
                  type="button"
                  :disabled="busyId === job.id"
                  @click="act(job, 'delete')"
                >删除</button>
              </div>
            </td>
          </tr>
          <tr v-if="!jobs.length">
            <td :colspan="showAll ? 7 : 5" class="hint">
              还没有任务。到「工作台」导入图片或 PDF 即可创建。
            </td>
          </tr>
        </tbody>
      </table>

      <p v-if="total > pageSize" class="row-between" style="margin-top: 12px">
        <span class="hint">共 {{ total }} 条，第 {{ page }} / {{ totalPages() }} 页</span>
        <span>
          <button class="ghost" type="button" :disabled="page <= 1" @click="go(-1)">上一页</button>
          <button class="ghost" type="button" :disabled="page >= totalPages()" @click="go(1)">下一页</button>
        </span>
      </p>
    </div>
  </div>
</template>