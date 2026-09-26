<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import store from '../store'

const router = useRouter()
const isAdmin = computed(() => !!store.state.user && store.state.user.role === 'admin')
const scope = ref('all')
const keyword = ref('')
const result = ref(null)
const error = ref('')
const busy = ref(false)

const STATUS_LABELS = {
  pending: '待提交',
  queued: '排队中',
  running: '识别中',
  done: '成功',
  empty: '无文字',
  failed: '失败',
  skipped: '已跳过',
  draft: '待提交',
  partial: '部分完成',
  canceled: '已取消',
}

function label(value) {
  return STATUS_LABELS[value] || value
}

async function run() {
  const word = keyword.value.trim()
  if (!word) {
    error.value = '请输入要检索的关键字'
    return
  }
  busy.value = true
  try {
    const suffix = (isAdmin.value && scope.value === 'all') ? '&scope=all' : ''
    result.value = await api('GET', '/api/search?q=' + encodeURIComponent(word) + suffix)
    error.value = ''
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

function openJob(jobId) {
  router.push({ name: 'job-detail', params: { id: jobId } })
}
</script>

<template>
  <div>
    <div class="card">
      <h2>历史检索</h2>
      <p class="hint">
        在任务标题、文件名与识别文本开头中查找关键字。完整的识别文本请到任务详情页导出
        后检索。
      </p>
      <div class="option-row">
        <label>
          关键字
          <input v-model="keyword" class="title-input" placeholder="例如：发票、合同编号" @keyup.enter="run" />
        </label>
        <label v-if="isAdmin">
          范围
          <select v-model="scope" @change="run">
            <option value="all">全部用户</option>
            <option value="mine">只看我的</option>
          </select>
        </label>
        <label>&nbsp;<button type="button" :disabled="busy" @click="run">{{ busy ? '检索中…' : '检索' }}</button></label>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-else-if="result" class="hint">
        关键字「{{ result.keyword }}」命中 {{ result.jobs.length }} 个任务、{{ result.items.length }} 个文件。{{ result.note }}
      </p>
    </div>

    <div v-if="result && result.jobs.length" class="card">
      <h2>命中的任务</h2>
      <table class="table">
        <thead><tr><th>任务</th><th v-if="isAdmin && scope === 'all'">用户</th><th>状态</th><th>进度</th><th>创建时间</th></tr></thead>
        <tbody>
          <tr v-for="job in result.jobs" :key="job.id">
            <td><a href="javascript:void(0)" @click="openJob(job.id)">{{ job.title }}</a></td>
            <td v-if="isAdmin && scope === 'all'">{{ job.user_display_name || job.username || job.user_id }}</td>
            <td><span class="badge">{{ label(job.status) }}</span></td>
            <td>{{ job.item_done }} / {{ job.item_total }}</td>
            <td class="hint">{{ job.created_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="result && result.items.length" class="card">
      <h2>命中的文件</h2>
      <table class="table">
        <thead><tr><th>文件名</th><th>所属任务</th><th v-if="isAdmin && scope === 'all'">用户</th><th>状态</th><th>命中片段</th></tr></thead>
        <tbody>
          <tr v-for="item in result.items" :key="item.id">
            <td class="ellipsis">{{ item.original_name }}</td>
            <td>
              <a href="javascript:void(0)" @click="openJob(item.job_id)">{{ item.job_title }}</a>
            </td>
            <td v-if="isAdmin && scope === 'all'">{{ item.username || item.user_id }}</td>
            <td><span class="badge">{{ label(item.status) }}</span></td>
            <td class="hint">{{ item.snippet || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="result && !result.jobs.length && !result.items.length" class="card">
      <p class="hint">没有找到匹配的记录。</p>
    </div>
  </div>
</template>