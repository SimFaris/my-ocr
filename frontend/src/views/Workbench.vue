<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, getCsrfToken } from '../api'

const router = useRouter()

const sourceType = ref('image')       // image | pdf
const title = ref('')
const entries = ref([])
const imageOptions = ref({})
const docOptions = ref({})
const selectedImage = ref({})
const selectedDoc = ref({})
const wantedLayered = ref(false)
const busy = ref(false)
const error = ref('')
const stage = ref('')
const dragging = ref(false)

let counter = 0
const IMAGE_KEYS = ['ocr.language', 'tbpu.parser', 'ocr.limit_side_len', 'ocr.maxSideLen']
const DOC_KEYS = ['ocr.language', 'tbpu.parser', 'doc.extractionMode']

const isPdf = computed(() => sourceType.value === 'pdf')

function fieldsOf(schema, keys) {
  return keys
    .filter((key) => schema[key] && schema[key].optionsList)
    .map((key) => Object.assign({ key: key }, schema[key]))
}

const optionFields = computed(() =>
  isPdf.value ? fieldsOf(docOptions.value, DOC_KEYS) : fieldsOf(imageOptions.value, IMAGE_KEYS),
)
const selected = computed(() => (isPdf.value ? selectedDoc.value : selectedImage.value))
const readyCount = computed(() => entries.value.filter((item) => item.status === 'ready').length)
const totalSize = computed(() => entries.value.reduce((sum, item) => sum + item.size, 0))

onMounted(async () => {
  try {
    imageOptions.value = (await api('GET', '/api/system/ocr-options')) || {}
    const initialImage = {}
    for (const field of fieldsOf(imageOptions.value, IMAGE_KEYS)) initialImage[field.key] = field.default
    selectedImage.value = initialImage
  } catch (err) {
    error.value = '读取图片识别参数失败：' + err.message
  }
  try {
    docOptions.value = (await api('GET', '/api/system/doc-options')) || {}
    const initialDoc = {}
    for (const field of fieldsOf(docOptions.value, DOC_KEYS)) initialDoc[field.key] = field.default
    selectedDoc.value = initialDoc
  } catch (err) {
    // 文档参数取不到不影响使用，引擎会用默认值
    docOptions.value = {}
  }
})

function switchSource(next) {
  if (next === sourceType.value) return
  if (entries.value.length && !window.confirm('切换来源会清空当前已选文件，继续吗？')) return
  sourceType.value = next
  entries.value = []
  error.value = ''
}

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
    error.value = '请先选择要识别的文件'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const jobOptions = Object.assign({}, selected.value)
    if (isPdf.value && wantedLayered.value) {
      jobOptions.laying_pdf = true
    }

    stage.value = '正在创建任务…'
    const created = await api('POST', '/api/jobs', {
      json: {
        title: title.value.trim() || ((isPdf.value ? 'PDF 任务 ' : '图片任务 ') + new Date().toLocaleString()),
        source_type: sourceType.value,
        ocr_options: jobOptions,
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
    if (!entries.value.some((item) => item.status === 'uploaded')) throw new Error('没有成功上传的文件')

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
      <h2>批量导入</h2>
      <div class="row" style="justify-content: flex-start; margin: 0 0 6px">
        <button class="ghost" type="button" :class="{ active: !isPdf }" @click="switchSource('image')">图片</button>
        <button class="ghost" type="button" :class="{ active: isPdf }" @click="switchSource('pdf')">PDF 文档</button>
      </div>

      <p v-if="!isPdf" class="hint">
        支持多选、拖拽、整文件夹导入。格式：jpg / jpeg / jfif / png / webp / bmp / tif / tiff。
      </p>
      <p v-else class="hint">
        支持多选 PDF（扫描件或电子文档）。扫描件按页识别，可选择同时产出双层可搜索 PDF。
      </p>

      <div
        class="dropzone"
        :class="{ active: dragging }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <p>把文件拖到这里，或使用下面的按钮选择</p>
        <div class="row">
          <label class="btn">
            {{ isPdf ? '选择 PDF 文件' : '选择图片' }}
            <input
              type="file"
              multiple
              :accept="isPdf ? '.pdf,application/pdf' : 'image/*,.tif,.tiff'"
              @change="onPick"
            />
          </label>
          <label v-if="!isPdf" class="btn ghost">
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
      <p v-else class="hint">识别参数暂不可用（引擎未就绪时读不到），将使用引擎默认值。</p>

      <p v-if="isPdf" class="kv-inline">
        <label class="checkbox">
          <input v-model="wantedLayered" type="checkbox" />
          生成双层可搜索 PDF（在原扫描图上叠加文字层，可复制可检索）
        </label>
      </p>
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