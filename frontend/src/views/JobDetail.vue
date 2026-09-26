<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const jobId = route.params.id

const job = ref(null)
const items = ref([])
const error = ref('')
const runtime = ref(null)
const activeItem = ref(null)
const activeText = ref('')
const textLoading = ref(false)
const saving = ref(false)
const savedAt = ref('')
const actionBusy = ref(false)
let timer = null

const STATUS_LABELS = {
  pending: '待提交',
  queued: '排队中',
  running: '识别中',
  done: '成功',
  empty: '无文字',
  failed: '失败',
  skipped: '已跳过',
}
const STATUS_CLASS = {
  done: 'up',
  failed: 'down',
  running: 'warn',
  queued: 'warn',
  empty: 'warn',
  skipped: '',
  pending: '',
}

const isActive = computed(() => !!job.value && ['queued', 'running'].indexOf(job.value.status) >= 0)
const failedCount = computed(() => items.value.filter((item) => item.status === 'failed').length)
const hasEditableText = computed(
  () => !!activeItem.value && ['done', 'empty'].indexOf(activeItem.value.status) >= 0,
)

function label(value) {
  return STATUS_LABELS[value] || value
}

function badgeClass(value) {
  return STATUS_CLASS[value] || ''
}

function seconds(ms) {
  if (!ms) return '-'
  return (ms / 1000).toFixed(1) + ' s'
}

async function load() {
  try {
    const data = await api('GET', '/api/jobs/' + jobId + '/events')
    job.value = data.job
    items.value = data.items
    runtime.value = data.runtime
    error.value = ''
    if (activeItem.value) {
      const fresh = data.items.filter((item) => item.id === activeItem.value.id)[0]
      if (fresh) activeItem.value = fresh
    }
  } catch (err) {
    error.value = err.message
  }
}

onMounted(async () => {
  await load()
  timer = window.setInterval(() => {
    if (isActive.value) load()
  }, 1500)
})

onUnmounted(() => {
  if (timer) {
    window.clearInterval(timer)
  }
})

async function selectItem(item) {
  activeItem.value = item
  activeText.value = ''
  savedAt.value = ''
  textLoading.value = true
  try {
    const response = await api('GET', '/api/items/' + item.id + '/text', { raw: true })
    activeText.value = await response.text()
  } catch (err) {
    error.value = err.message
  } finally {
    textLoading.value = false
  }
}

async function saveText() {
  if (!activeItem.value) return
  saving.value = true
  try {
    await api('PUT', '/api/items/' + activeItem.value.id + '/text', { json: { text: activeText.value } })
    savedAt.value = new Date().toLocaleTimeString()
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

async function act(action) {
  if (action === 'delete' && !window.confirm('确定删除该任务及其文件吗？')) return
  if (action === 'cancel' && !window.confirm('确定取消该任务吗？')) return
  actionBusy.value = true
  try {
    if (action === 'cancel') {
      await api('POST', '/api/jobs/' + jobId + '/cancel')
    } else if (action === 'retry') {
      await api('POST', '/api/jobs/' + jobId + '/retry')
    } else if (action === 'delete') {
      await api('DELETE', '/api/jobs/' + jobId)
      router.push({ name: 'jobs' })
      return
    }
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    actionBusy.value = false
  }
}

function exportUrl(format, scope) {
  return '/api/jobs/' + jobId + '/export?format=' + format + '&scope=' + scope
}

function downloadItemText(item) {
  window.open('/api/items/' + item.id + '/text', '_blank')
}
</script>

<template>
  <div v-if="job">
    <div class="card">
      <div class="row-between">
        <h2>{{ job.title }}</h2>
        <div>
          <span class="badge" :class="badgeClass(job.status)">{{ label(job.status) }}</span>
          <span class="hint">　{{ job.item_done }} / {{ job.item_total }} 完成</span>
          <span v-if="job.item_failed" class="error">　失败 {{ job.item_failed }}</span>
        </div>
      </div>

      <div class="kv">
        <span class="key">任务编号</span>
        <span>{{ job.id }}</span>
        <span class="key">创建 / 开始 / 结束</span>
        <span>{{ job.created_at }} / {{ job.started_at || '-' }} / {{ job.finished_at || '-' }}</span>
        <span class="key">识别工作线程</span>
        <span>{{ runtime ? (runtime.alive + ' / ' + runtime.workers + ' 运行中') : '未启用' }}</span>
      </div>

      <div class="actions">
        <button class="ghost" type="button" @click="router.push({ name: 'jobs' })">返回列表</button>
        <button
          v-if="['draft', 'queued', 'running'].indexOf(job.status) >= 0"
          class="ghost"
          type="button"
          :disabled="actionBusy"
          @click="act('cancel')"
        >取消任务</button>
        <button
          v-if="failedCount > 0"
          class="ghost"
          type="button"
          :disabled="actionBusy"
          @click="act('retry')"
        >重试失败项（{{ failedCount }}）</button>
        <a class="btn ghost" :href="exportUrl('txt', 'all')">导出全部 txt</a>
        <a class="btn ghost" :href="exportUrl('csv', 'all')">导出全部 csv</a>
        <a class="btn ghost" :href="exportUrl('txt', 'success')">仅导出成功项 txt</a>
        <button class="ghost" type="button" :disabled="actionBusy" @click="act('delete')">删除任务</button>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <div class="card">
      <div class="detail-grid">
        <div>
          <h2>文件列表</h2>
          <table class="table">
            <thead>
              <tr><th>#</th><th>文件名</th><th>状态</th><th>字数</th><th>耗时</th></tr>
            </thead>
            <tbody>
              <tr
                v-for="item in items"
                :key="item.id"
                :style="{ cursor: 'pointer', background: activeItem && activeItem.id === item.id ? '#eff6ff' : '' }"
                @click="selectItem(item)"
              >
                <td>{{ item.seq }}</td>
                <td class="ellipsis">{{ item.original_name }}</td>
                <td>
                  <span class="badge" :class="badgeClass(item.status)">{{ label(item.status) }}</span>
                </td>
                <td>{{ item.char_count === null || item.char_count === undefined ? '-' : item.char_count }}</td>
                <td class="hint">{{ seconds(item.duration_ms) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div>
          <h2>{{ activeItem ? '预览与识别文本' : '点击左侧文件查看结果' }}</h2>
          <template v-if="activeItem">
            <p class="hint">
              {{ activeItem.original_name }}
              <span v-if="activeItem.error_message" class="error">　{{ activeItem.error_message }}</span>
            </p>
            <img class="preview-image" :src="'/api/items/' + activeItem.id + '/preview'" alt="原图预览" />
            <p v-if="textLoading" class="hint">正在读取文本…</p>
            <textarea v-else v-model="activeText" class="textarea" :readonly="!hasEditableText"></textarea>
            <div class="actions">
              <button type="button" :disabled="saving || !hasEditableText" @click="saveText">
                {{ saving ? '保存中…' : '保存校对结果' }}
              </button>
              <button class="ghost" type="button" @click="downloadItemText(activeItem)">下载该项 txt</button>
              <span v-if="savedAt" class="hint">已于 {{ savedAt }} 保存</span>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="card">
    <p v-if="error" class="error">{{ error }}</p>
    <p v-else class="hint">正在加载任务…</p>
  </div>
</template>