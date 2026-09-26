<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, getCsrfToken } from '../api'
import { captureFileName, clampRect, rotateSize, scaleRect, selectionToRect } from '../utils/image'

const router = useRouter()

const state = ref('checking')      // checking | ready | insecure | denied | no-camera | busy | error
const message = ref('')
const devices = ref([])
const deviceId = ref('')
const shots = ref([])
const activeId = ref(null)
const cropRect = ref(null)
const dragging = ref(false)
const title = ref('')
const ocrOptions = ref({})
const selected = ref({})
const busy = ref(false)
const stage = ref('')
const httpsPort = ref(8443)
const certExists = ref(false)

const videoEl = ref(null)
const previewEl = ref(null)
let stream = null
let dragStart = null
let counter = 0
const IMAGE_KEYS = ['ocr.language', 'tbpu.parser', 'ocr.limit_side_len', 'ocr.maxSideLen']

const activeShot = computed(() => shots.value.filter((item) => item.id === activeId.value)[0] || null)
const optionFields = computed(() => IMAGE_KEYS
  .filter((key) => ocrOptions.value[key] && ocrOptions.value[key].optionsList)
  .map((key) => Object.assign({ key: key }, ocrOptions.value[key])))

const secureUrl = computed(() => {
  const host = window.location.hostname || '服务器IP'
  return 'https://' + host + ':' + httpsPort.value + '/'
})

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

async function loadSystemInfo() {
  try {
    const data = await api('GET', '/api/system/status')
    if (data && data.https) {
      httpsPort.value = data.https.port || 8443
      certExists.value = !!data.https.cert_exists
    }
  } catch (err) {
    // 状态接口取不到不影响拍照说明
  }
}

async function loadOcrOptions() {
  try {
    ocrOptions.value = (await api('GET', '/api/system/ocr-options')) || {}
    const initial = {}
    for (const field of optionFields.value) initial[field.key] = field.default
    selected.value = initial
  } catch (err) {
    ocrOptions.value = {}
  }
}

function describeError(error) {
  const name = error && error.name
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return { state: 'denied', message: '浏览器拒绝了摄像头权限。请点击地址栏左侧的锁/摄像头图标，把摄像头改为「允许」后点击下方按钮重试。' }
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return { state: 'no-camera', message: '没有找到可用的摄像头，请确认 USB 摄像头已插好并被系统识别。' }
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return { state: 'busy', message: '摄像头被其他程序占用（例如系统的相机应用、会议软件）。请关掉它们后重试。' }
  }
  if (name === 'OverconstrainedError') {
    return { state: 'error', message: '所选摄像头不支持请求的分辨率，请换一个设备再试。' }
  }
  return { state: 'error', message: '无法打开摄像头：' + ((error && error.message) || '未知错误') }
}

async function refreshDevices() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return
  try {
    const list = await navigator.mediaDevices.enumerateDevices()
    devices.value = list.filter((item) => item.kind === 'videoinput')
    if (!deviceId.value && devices.value.length) {
      deviceId.value = devices.value[0].deviceId
    }
  } catch (err) {
    devices.value = []
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop())
    stream = null
  }
  if (videoEl.value) {
    videoEl.value.srcObject = null
  }
}

async function startCamera(exactId) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    state.value = 'error'
    message.value = '当前浏览器不支持摄像头接口（getUserMedia），请改用 Chrome、Edge、Firefox 或 Safari 的较新版本。'
    return
  }
  stopCamera()
  message.value = ''
  const video = { width: { ideal: 1920 }, height: { ideal: 1080 } }
  const wanted = exactId || deviceId.value
  if (wanted) video.deviceId = { exact: wanted }

  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: video, audio: false })
    await nextTick()
    if (videoEl.value) {
      videoEl.value.srcObject = stream
      await videoEl.value.play()
    }
    state.value = 'ready'
    await refreshDevices()
  } catch (error) {
    const described = describeError(error)
    state.value = described.state
    message.value = described.message
  }
}

function onDeviceChange() {
  refreshDevices()
}

function onPointerDown(event) {
  if (!activeShot.value) return
  const box = event.currentTarget.getBoundingClientRect()
  dragStart = { x: event.clientX - box.left, y: event.clientY - box.top }
  cropRect.value = selectionToRect(dragStart, dragStart)
  dragging.value = true
}

function onPointerMove(event) {
  if (!dragging.value || !dragStart) return
  const box = event.currentTarget.getBoundingClientRect()
  const end = {
    x: Math.max(0, Math.min(event.clientX - box.left, box.width)),
    y: Math.max(0, Math.min(event.clientY - box.top, box.height)),
  }
  cropRect.value = selectionToRect(dragStart, end)
}

function onPointerUp() {
  dragging.value = false
  if (cropRect.value && (cropRect.value.width < 8 || cropRect.value.height < 8)) {
    cropRect.value = null
  }
}

function toBlob(canvas) {
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92))
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('图片解码失败'))
    image.src = url
  })
}

function replaceShot(shot, blob, width, height) {
  URL.revokeObjectURL(shot.url)
  shot.blob = blob
  shot.url = URL.createObjectURL(blob)
  shot.width = width
  shot.height = height
  cropRect.value = null
}

async function capture() {
  const video = videoEl.value
  if (!video || !video.videoWidth) {
    message.value = '画面还没准备好，请稍等一下再拍。'
    return
  }
  const width = video.videoWidth
  const height = video.videoHeight
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  context.drawImage(video, 0, 0, width, height)
  const blob = await toBlob(canvas)

  counter += 1
  const url = URL.createObjectURL(blob)
  const shot = {
    id: counter,
    name: captureFileName(counter),
    blob: blob,
    url: url,
    width: width,
    height: height,
    original: { blob: blob, width: width, height: height },
  }
  shots.value.push(shot)
  activeId.value = shot.id
  cropRect.value = null
}

async function rotate(degrees) {
  const shot = activeShot.value
  if (!shot) return
  const size = rotateSize({ width: shot.width, height: shot.height }, degrees)
  const image = await loadImage(shot.url)
  const canvas = document.createElement('canvas')
  canvas.width = size.width
  canvas.height = size.height
  const context = canvas.getContext('2d')
  context.translate(size.width / 2, size.height / 2)
  context.rotate((degrees * Math.PI) / 180)
  context.drawImage(image, -shot.width / 2, -shot.height / 2)
  const blob = await toBlob(canvas)
  replaceShot(shot, blob, size.width, size.height)
}

async function applyCrop() {
  const shot = activeShot.value
  if (!shot || !cropRect.value || !previewEl.value) return
  const display = { width: previewEl.value.clientWidth, height: previewEl.value.clientHeight }
  const rect = clampRect(
    scaleRect(cropRect.value, display, { width: shot.width, height: shot.height }),
    { width: shot.width, height: shot.height },
  )
  if (rect.width < 16 || rect.height < 16) {
    message.value = '裁剪范围太小，请重新框选。'
    return
  }
  const image = await loadImage(shot.url)
  const canvas = document.createElement('canvas')
  canvas.width = rect.width
  canvas.height = rect.height
  const context = canvas.getContext('2d')
  context.drawImage(image, rect.x, rect.y, rect.width, rect.height, 0, 0, rect.width, rect.height)
  const blob = await toBlob(canvas)
  replaceShot(shot, blob, rect.width, rect.height)
  message.value = ''
}

async function resetShot() {
  const shot = activeShot.value
  if (!shot) return
  const original = shot.original
  replaceShot(shot, original.blob, original.width, original.height)
}

function removeShot(shot) {
  URL.revokeObjectURL(shot.url)
  shots.value = shots.value.filter((item) => item.id !== shot.id)
  if (activeId.value === shot.id) {
    activeId.value = shots.value.length ? shots.value[shots.value.length - 1].id : null
  }
}

function clearShots() {
  shots.value.forEach((shot) => URL.revokeObjectURL(shot.url))
  shots.value = []
  activeId.value = null
  cropRect.value = null
}

function uploadShot(jobId, shot, token) {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', new File([shot.blob], shot.name, { type: 'image/jpeg' }))
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/jobs/' + jobId + '/items')
    xhr.setRequestHeader('X-CSRF-Token', token)
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve()
        return
      }
      let detail = 'HTTP ' + xhr.status
      try {
        const payload = JSON.parse(xhr.responseText)
        if (payload && payload.error && payload.error.message) detail = payload.error.message
      } catch (err) {
        detail = 'HTTP ' + xhr.status
      }
      reject(new Error(detail))
    }
    xhr.onerror = () => reject(new Error('网络错误'))
    xhr.send(form)
  })
}

async function startRecognize() {
  if (!shots.value.length) {
    message.value = '请先拍摄至少一张照片。'
    return
  }
  busy.value = true
  message.value = ''
  try {
    stage.value = '正在创建任务…'
    const created = await api('POST', '/api/jobs', {
      json: {
        title: title.value.trim() || ('拍照任务 ' + new Date().toLocaleString()),
        source_type: 'camera',
        ocr_options: selected.value,
      },
    })
    const jobId = created.job.id
    const token = getCsrfToken()

    let index = 0
    for (const shot of shots.value) {
      index += 1
      stage.value = '正在上传 ' + index + '/' + shots.value.length + '：' + shot.name
      await uploadShot(jobId, shot, token)
    }

    stage.value = '正在提交识别任务…'
    await api('POST', '/api/jobs/' + jobId + '/start')
    clearShots()
    router.push({ name: 'job-detail', params: { id: jobId } })
  } catch (err) {
    message.value = err.message
  } finally {
    busy.value = false
    stage.value = ''
  }
}

onMounted(async () => {
  if (!window.isSecureContext) {
    state.value = 'insecure'
    loadSystemInfo()
    return
  }
  loadOcrOptions()
  await startCamera()
  if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
    navigator.mediaDevices.addEventListener('devicechange', onDeviceChange)
  }
})

onUnmounted(() => {
  if (navigator.mediaDevices && navigator.mediaDevices.removeEventListener) {
    navigator.mediaDevices.removeEventListener('devicechange', onDeviceChange)
  }
  stopCamera()
  clearShots()
})
</script>

<template>
  <div>
    <div v-if="state === 'insecure'" class="card">
      <h2>拍照功能需要通过 HTTPS 访问</h2>
      <p>
        浏览器规定：只有安全上下文（HTTPS 或 localhost）才允许调用摄像头。你现在是通过
        <b>http</b> 打开页面的，所以拍摄功能被浏览器禁用，其余功能（导入图片、导入 PDF、
        查看结果）不受影响。
      </p>
      <p>
        解决步骤：先在<b>同一台电脑</b>上导入服务器的根证书，然后用 https 地址重新打开页面。
      </p>
      <ol class="steps">
        <li>
          下载根证书：
          <a class="btn ghost" href="/api/system/root-cert">下载 my-ocr-root-ca.cer</a>
          <span v-if="!certExists" class="hint">　（服务端尚未生成证书，请先运行 tools/gen_cert.py）</span>
        </li>
        <li>双击该文件 → 安装证书 → 存储位置选「本地计算机」→ 放入「受信任的根证书颁发机构」。</li>
        <li>
          用加密地址打开本系统：
          <a class="btn ghost" :href="secureUrl">前往 {{ secureUrl }}</a>
        </li>
        <li>在 https 页面里再回到「拍照」，浏览器会询问摄像头权限，选择允许。</li>
      </ol>
      <p class="hint">
        也可以用管理员身份运行 tools\import_root_cert.bat，效果一样。
        macOS 上 Safari 需要把证书加入「钥匙串访问 → 系统 → 证书」，并设为「始终信任」。
      </p>
    </div>

    <template v-else>
      <div class="card">
        <div class="row-between">
          <h2>拍照导入</h2>
          <div class="row-between">
            <select v-if="devices.length > 1" :value="deviceId" @change="startCamera($event.target.value)">
              <option v-for="item in devices" :key="item.deviceId" :value="item.deviceId">
                {{ item.label || ('摄像头 ' + (devices.indexOf(item) + 1)) }}
              </option>
            </select>
            <button class="ghost" type="button" @click="startCamera()">重新连接</button>
          </div>
        </div>

        <p v-if="message" class="error">{{ message }}</p>

        <div v-if="state === 'ready'" class="camera-grid">
          <div>
            <video ref="videoEl" class="video" playsinline autoplay muted></video>
            <div class="actions">
              <button type="button" @click="capture">拍摄</button>
              <span class="hint">可连续拍摄多张；拍完在右侧点选进行旋转或裁剪。</span>
            </div>
          </div>
          <div>
            <h3 class="sub">已拍摄 {{ shots.length }} 张</h3>
            <div class="thumbs">
              <div
                v-for="shot in shots"
                :key="shot.id"
                class="thumb"
                :class="{ active: shot.id === activeId }"
                @click="activeId = shot.id"
              >
                <img :src="shot.url" :alt="shot.name" />
                <div class="thumb-info">
                  <span>{{ shot.name }}</span>
                  <button class="link" type="button" @click.stop="removeShot(shot)">删除</button>
                </div>
              </div>
              <p v-if="!shots.length" class="hint">还没有拍摄。</p>
            </div>
          </div>
        </div>

        <div v-else-if="state !== 'insecure'" class="row">
          <button type="button" @click="startCamera()">允许并打开摄像头</button>
        </div>
      </div>

      <div v-if="activeShot" class="card">
        <h2>调整画面（{{ activeShot.name }}）</h2>
        <p class="hint">在图片上按住拖动可框选裁剪区域；旋转按钮每次转 90 度。</p>
        <div
          class="crop-area"
          @pointerdown="onPointerDown"
          @pointermove="onPointerMove"
          @pointerup="onPointerUp"
          @pointerleave="onPointerUp"
        >
          <img ref="previewEl" class="crop-image" :src="activeShot.url" alt="拍摄结果" draggable="false" />
          <div
            v-if="cropRect"
            class="crop-box"
            :style="{ left: cropRect.x + 'px', top: cropRect.y + 'px', width: cropRect.width + 'px', height: cropRect.height + 'px' }"
          ></div>
        </div>
        <div class="actions">
          <button class="ghost" type="button" @click="rotate(-90)">向左旋转 90°</button>
          <button class="ghost" type="button" @click="rotate(90)">向右旋转 90°</button>
          <button type="button" :disabled="!cropRect" @click="applyCrop">应用裁剪</button>
          <button class="ghost" type="button" @click="cropRect = null">取消选区</button>
          <button class="ghost" type="button" @click="resetShot">还原</button>
        </div>
      </div>

      <div class="card">
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

        <p v-if="stage" class="hint">{{ stage }}</p>
        <div class="actions">
          <button type="button" :disabled="busy || !shots.length" @click="startRecognize">
            {{ busy ? '处理中…' : ('开始识别（' + shots.length + ' 张）') }}
          </button>
          <button class="ghost" type="button" :disabled="busy || !shots.length" @click="clearShots">清空已拍摄</button>
        </div>
      </div>
    </template>
  </div>
</template>