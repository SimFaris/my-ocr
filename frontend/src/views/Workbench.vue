<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, getCsrfToken } from '../api'

const router = useRouter()

const title = ref('')
const entries = ref([])
const options = ref({})
const selected = ref({})
const busy = ref(false)
const error = ref('')
const stage = ref('')
const dragging = ref(false)

let counter = 0
const OPTION_KEYS = ['ocr.language', 'ocr.cls', 'ocr.angle', 'ocr.limit_side_len', 'ocr.maxSideLen', 'tbpu.parser']

const optionFields = computed(() =>
  OPTION_KEYS
    .filter((key) => options.value[key] && options.value[key].optionsList)
    .map((key) => Object.assign({ key: key }, options.value[key])),
)

const readyCount = computed(() => entries.value.filter((item) => item.status === 'ready').length)
const totalSize = computed(() => entries.value.reduce((sum, item) => sum + item.size, 0))

onMounted(async () => {
  try {
    options.value = (await api('GET', '/api/system/ocr-options')) || {}
    const initial = {}
    for (const field of optionFields.value) {
      initial[field.key] = field.default
    }
    selected.value = initial
  } catch (err) {
    error.value = '读取识别参数失败：' + err.message
  }
})

function addFiles(list) {
  for (const file of Array.from(list || [])) {
    counter += 1
    entries.value.push({
      key: counter,
      file: file,
      name: file.name,
      size: file.size,
      status: 'ready',
      progress: 0,
      error: '',
    })
  }
}

function onPick(event) {
  addFiles(event.target.files)
  event.target.value = ''
}

function onDrop(event) {
  dragging.value = false
  addFiles(event.dataTransfer.files)
}

function removeEntry(entry) {
  entries.value = entries.value.filter((item) => item !== entry)
}

function clearAll() {
  entries.value = []
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function uploadOne(jobId, entry, token) {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', entry.file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/jobs/' + jobId + '/items')
    xhr.setRequestHeader('X-CSRF-Token', token)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        entry.progress = Math.round((event.loaded * 100) / event.total)
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        entry.status = 'uploaded'
        entry.progress = 100
        resolve()
        return
      }
      let message = 'HTTP ' + xhr.status
      try {
        const payload = JSON.parse(xhr.responseText)
        if (payload && payload.error && payload.error.message) message = payload.error.message
      } catch (err) {
        message = 'HTTP ' + xhr.status
      }
      entry.status = 'failed'
      entry.error = message
      reject(new Error(message))
    }
    xhr.onerror = () => {
      entry.status = 'failed'
      entry.error = '网络错误'
      reject(new Error('网络错误'))
    }
    xhr.send(form)
  })
}

async function startImport() {
  if (!entries.value.length) {
    error.value = '请先选择要识别的图片'
    return
  }
  busy.value = true
  error.value = ''
  try {
    stage.value = '正在创建任务…'
    const created = await api('POST', '/api/jobs', {
      json: {
        title: title.value.trim() || ('图片任务 ' + new Date().toLocaleString()),
        source_type: 'image',
        ocr_options: selected.value,
      },
    })
    const jobId = created.job.id
    const token = getCsrfToken()

    let index = 0
    for (const entry of entries.value) {
      index += 1
      if (entry.status === 'uploaded') continue
      stage.value = '正在上传 ' + index + '/' + entries.value.length + '：' + entry.name
      await uploadOne(jobId, entry, token)
    }
    const uploaded = entries.value.filter((item) => item.status === 'uploaded').length
    if (!uploaded) throw new Error('没有成功上传的文件')

    stage.value = '正在提交识别任务…'
    await api('POST', '/api/jobs/' + jobId + '/start')
    router.push({ name: 'job-detail', params: { id: jobId } })
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
    stage.value = ''
  }
}
</script>

<template>
  <div>
    <div class="card">
      <h2>批量导入图片</h2>
      <p class="hint">
        支持多选、拖拽、整文件夹导入。格式：jpg / jpeg / jfif / png / webp / bmp / tif / tiff。
        上传完成后自动进入识别队列。
      </p>

      <div
        class="dropzone"
        :class="{ active: dragging }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <p>把图片拖到这里，或使用下面的按钮选择</p>
        <div class="row">
          <label class="btn">
            选择图片
            <input type="file" multiple accept="image/*,.tif,.tiff" @change="onPick" />
          </label>
          <label class="btn ghost">
            选择整个文件夹
            <input type="file" webkitdirectory directory multiple @change="onPick" />
          </label>
          <button class="ghost" type="button" :disabled="!entries.length" @click="clearAll">清空列表</button>
        </div>
      </div>

      <p class="kv-inline">
        <label>
          任务名称
          <input v-model="title" class="title-input" placeholder="留空则自动命名" />
        </label>
      </p>

      <div v-if="optionFields.length" class="option-row">
        <label v-for="field in optionFields" :key="field.key">
          {{ field.title || field.key }}
          <select v-model="selected[field.key]">
            <option v-for="item in field.optionsList" :key="item[0]" :value="item[0]">{{ item[1] }}</option>
          </select>
        </label>
      </div>
      <p v-else class="hint">识别参数暂不可用（引擎未就绪时无法读取），将使用引擎默认值。</p>
    </div>

    <div v-if="entries.length" class="card">
      <h2>待导入文件（{{ entries.length }} 个，共 {{ formatSize(totalSize) }}）</h2>
      <table class="table">
        <thead>
          <tr><th style="width: 45%">文件名</th><th>大小</th><th>状态</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="entry in entries" :key="entry.key">
            <td class="ellipsis">{{ entry.name }}</td>
            <td>{{ formatSize(entry.size) }}</td>
            <td>
              <span v-if="entry.status === 'ready'" class="badge">待上传</span>
              <span v-else-if="entry.status === 'uploaded'" class="badge up">已上传</span>
              <span v-else-if="entry.status === 'failed'" class="badge down">失败：{{ entry.error }}</span>
              <span v-else class="badge warn">上传中 {{ entry.progress }}%</span>
            </td>
            <td>
              <button class="link" type="button" :disabled="busy" @click="removeEntry(entry)">移除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="stage" class="hint">{{ stage }}</p>
      <button type="button" :disabled="busy || !entries.length" @click="startImport">
        {{ busy ? '处理中…' : ('开始导入并识别（' + readyCount + ' 个待上传）') }}
      </button>
    </div>
  </div>
</template>