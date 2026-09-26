<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import store from '../store'

const status = ref(null)
const error = ref('')
const secureContext = ref(false)
const updatedAt = ref('')
let timer = null

const umi = computed(() => (status.value ? status.value.umi : null))
const queue = computed(() => (status.value ? status.value.queue : null))
const disk = computed(() => (status.value ? status.value.disk : null))

async function refresh() {
  try {
    status.value = await store.loadStatus()
    error.value = ''
    updatedAt.value = new Date().toLocaleTimeString()
  } catch (exception) {
    error.value = exception.message || '无法获取系统状态'
  }
}

onMounted(() => {
  secureContext.value = window.isSecureContext === true
  refresh()
  timer = window.setInterval(refresh, 5000)
})

onUnmounted(() => {
  if (timer) {
    window.clearInterval(timer)
  }
})
</script>

<template>
  <div>
    <div class="card">
      <h2>导入入口</h2>
      <div class="tiles">
        <div class="tile">
          <h3>批量导入图片</h3>
          <p>多选、拖拽或整个文件夹导入，支持 jpg/png/bmp/webp/tif 等格式。</p>
          <p class="hint">将在 M2 里程碑开放。</p>
        </div>
        <div class="tile">
          <h3>批量导入 PDF</h3>
          <p>逐页识别扫描件，可产出双层可搜索 PDF 与文本。</p>
          <p class="hint">将在 M3 里程碑开放。</p>
        </div>
        <div class="tile">
          <h3>USB 摄像头拍照</h3>
          <p v-if="secureContext">当前为安全上下文，可使用本机摄像头拍摄并识别。</p>
          <p v-else class="hint">
            当前通过 http 访问，浏览器禁止调用摄像头。请改用
            <a href="javascript:void(0)">https://本机地址:8443</a> 访问后使用（需先导入根证书）。
          </p>
          <p class="hint">拍摄功能将在 M4 里程碑开放。</p>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>OCR 引擎</h2>
      <p v-if="error" class="error">{{ error }}</p>
      <div v-if="umi" class="kv">
        <span class="key">状态</span>
        <span>
          <span class="badge" :class="umi.online ? 'up' : 'down'">
            {{ umi.online ? '在线' : '不可用' }}
          </span>
          <span v-if="!umi.online" class="hint"> 请确认 Umi-OCR 已启动并在全局设置中允许 HTTP 服务</span>
        </span>
        <span class="key">服务地址</span>
        <span>{{ umi.base_url }}</span>
        <span class="key">程序路径</span>
        <span>
          {{ umi.exe_path }}
          <span class="badge" :class="umi.exe_exists ? 'up' : 'warn'">
            {{ umi.exe_exists ? '已找到' : '未找到' }}
          </span>
        </span>
        <span class="key">托管进程</span>
        <span>{{ umi.process_running ? ('运行中，PID ' + umi.process_pid) : '未由本服务启动' }}</span>
        <span class="key">自动重启次数</span>
        <span>{{ umi.restarts }} / {{ umi.max_restarts }}</span>
        <span class="key">最近检查</span>
        <span>{{ umi.last_check || '尚未检查' }}</span>
        <span v-if="umi.last_error" class="key">最近错误</span>
        <span v-if="umi.last_error" class="error">{{ umi.last_error }}</span>
      </div>
    </div>

    <div class="card">
      <h2>队列与资源</h2>
      <div v-if="queue && disk" class="grid">
        <div class="metric">
          <div class="label">排队中</div>
          <div class="value">{{ queue.pending }}</div>
        </div>
        <div class="metric">
          <div class="label">识别中</div>
          <div class="value">{{ queue.running }}</div>
        </div>
        <div class="metric">
          <div class="label">已完成</div>
          <div class="value">{{ queue.done }}</div>
        </div>
        <div class="metric">
          <div class="label">失败</div>
          <div class="value">{{ queue.failed }}</div>
        </div>
        <div class="metric">
          <div class="label">磁盘可用</div>
          <div class="value">{{ disk.free_gb }} GB</div>
        </div>
      </div>
      <p v-else class="hint">正在读取…</p>
    </div>

    <div class="card">
      <h2>服务信息</h2>
      <div v-if="status" class="kv">
        <span class="key">版本</span>
        <span>{{ status.app_version }}</span>
        <span class="key">数据目录</span>
        <span>{{ status.data_dir }}</span>
        <span class="key">识别工作线程</span>
        <span>{{ status.workers }}</span>
        <span class="key">HTTPS</span>
        <span>
          <span class="badge" :class="status.https.cert_exists ? 'up' : 'warn'">
            {{ status.https.enabled ? ('端口 ' + status.https.port) : '未启用' }}
          </span>
          <span v-if="!status.https.cert_exists" class="hint"> 证书未生成，可执行 tools/gen_cert.py</span>
        </span>
        <span class="key">服务器时间</span>
        <span>{{ status.server_time }}</span>
        <span class="key">本次刷新</span>
        <span>{{ updatedAt }}</span>
      </div>
      <p style="margin: 14px 0 0">
        <button class="ghost" type="button" @click="refresh">立即刷新</button>
        <span class="hint">　状态每 5 秒自动刷新</span>
      </p>
    </div>
  </div>
</template>