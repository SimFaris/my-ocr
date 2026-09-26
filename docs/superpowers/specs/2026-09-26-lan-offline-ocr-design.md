# 局域网离线 OCR 系统 — 设计文档

| 项 | 内容 |
| --- | --- |
| 日期 | 2026-09-26 |
| 状态 | 已确认（待评审） |
| 目标平台 | Windows 7 SP1 x64（优先）/ Windows 10 x64 |
| OCR 引擎 | Umi-OCR v2.1.5（外部进程，HTTP 接口调用） |
| 后端 | Python 3.8.10 + Flask + cheroot |
| 前端 | Vue 3 + Vite（构建目标 es2017），纯浏览器，无需安装 |

---

## 1. 背景与目标

在无外网的内部局域网中提供一套 OCR 服务：服务端一台 Windows 机器集中运行，多用户通过浏览器同时使用，不需要在客户端安装任何软件。OCR 能力直接复用现有开源软件 Umi-OCR，本项目不实现识别算法，只做工程化封装。

目标：

1. 多用户并发访问，互不干扰，单个大任务不阻塞其他人。
2. 支持批量导入图片、批量导入 PDF、调用用户本机 USB 摄像头拍照导入。
3. 服务端可在 Windows 7 SP1 x64 上运行（这条决定 Python 版本与全部依赖选型）。
4. 客户端覆盖 Windows / macOS / Linux 上的主流近年浏览器，无需安装插件。
5. 识别结果可查看、可人工校对、可导出。

---

## 2. 范围

### 2.1 范围内

- 账号体系：登录、注销、改密码；角色分管理员与普通用户。
- 批量导入图片（多选、拖拽、整个文件夹）与 PDF（多选）。
- 浏览器调用用户本机 USB 摄像头，支持选择设备、连拍多张、拍摄后裁剪与旋转。
- 任务队列：排队、执行、进度、取消、重试失败项。
- 识别结果：逐项查看、编辑保存、复制、搜索。
- 导出：txt、csv、xlsx、jsonl；PDF 任务额外支持导出 Umi-OCR 生成的双层可搜索 PDF。
- 结果与原始文件的保留策略、自动清理。
- 管理员功能：用户管理、参数设置、磁盘与引擎状态查看。
- HTTPS 自签证书的生成、分发与客户端导入指引。
- 离线部署包与部署文档（Win7 / Win10）。

### 2.2 范围外（明确不做）

- 不实现 OCR 算法，不做模型训练或更换引擎的适配层（引擎由 Umi-OCR 插件体系负责）。
- 不做表格结构还原为 Excel（Umi-OCR 不支持按单元格还原）。
- 不做翻译、数学公式识别、二维码独立功能页。
- 不做服务端图片缩略图生成（避免引入 Pillow 等 C 扩展依赖）。
- 不做多机分布式部署，单台服务机。
- 不做移动端专门适配（页面可打开，但不针对手机做布局优化）。
- 不集成 AD / LDAP（后续可加，本期用本地账号）。
- 不做断点续传、分片上传（单文件上限内一次传完）。

### 2.3 已知局限

- 浏览器不支持的图片格式（如 TIFF）无法在页面上预览，任务列表显示占位图标与文件名，识别流程不受影响。
- 双层可搜索 PDF 由 Umi-OCR 生成，排版还原度取决于其引擎能力。
- 单机磁盘容量即系统容量上限。

---

## 3. 约束与前提

| 约束 | 内容 | 影响 |
| --- | --- | --- |
| 操作系统 | Win7 SP1 x64 需可运行 | Python 必须 ≤ 3.8.10（3.9 起要求 Win8.1+）；依赖必须全为纯 Python |
| 网络 | 与公网物理隔离 | 前端不得引用任何 CDN；依赖需离线打包 |
| 浏览器 | Chrome/Edge ≥ 90、Firefox ≥ 90、Safari ≥ 14（Win7 上限为 Chrome/Edge 109、Firefox 115 ESR） | 可用 ES2017 语法与 Vue 3；不支持 IE11 |
| 摄像头 | 位于用户本机，浏览器直接调用 | 必须 HTTPS（安全上下文要求），http 访问时关闭拍照入口 |
| Umi-OCR 并发 | 官方文档明确"对并发支持较差，尽量不要并发调用"，大批量连续调用偶发 `connect ECONNREFUSED` | 后端必须串行化调用并实现重试，禁止客户端直连 Umi-OCR |
| Umi-OCR 版本 | 文档识别（PDF）需 ≥ 2.1.4 | 部署要求 v2.1.4+，目标 v2.1.5 |

---

## 4. 总体架构

### 4.1 部署拓扑

```
┌─────────────────────────┐
│ 用户 A 浏览器 (任意系统) │──┐
├─────────────────────────┤  │    http://server:8080
│ 用户 B 浏览器 + USB摄像头│──┼──▶ https://server:8443   （摄像头必需）
├─────────────────────────┤  │
│ 用户 C 浏览器            │──┘
└─────────────────────────┘
                      │  局域网
                      ▼
        ┌──────────────────────────────────────┐
        │ 服务机 (Windows 7 SP1 x64 / Win10)    │
        │                                      │
        │  ┌────────────────────────────────┐  │
        │  │ OCR 服务 (Python 3.8.10)       │  │
        │  │  Flask + cheroot              │  │
        │  │  认证 / REST API / 静态前端     │  │
        │  │  调度器 + 工作线程              │  │
        │  │  SQLite(WAL) + 文件存储         │  │
        │  │  自签证书 (https)               │  │
        │  └───────────────┬────────────────┘  │
        │                  │ HTTP 127.0.0.1:1224│
        │  ┌───────────────▼────────────────┐  │
        │  │ Umi-OCR.exe (被托管，不对外暴露) │  │
        │  └────────────────────────────────┘  │
        └──────────────────────────────────────┘
```

### 4.2 组件职责

| 组件 | 职责 | 边界 |
| --- | --- | --- |
| Flask 应用 | 路由、认证、参数校验、静态前端托管 | 不直接调用 Umi-OCR，只操作队列与数据库 |
| 调度器 | 从数据库取待办项，按用户轮转投递给工作线程 | 唯一决定"谁先执行"的地方 |
| 工作线程 | 执行单个任务项：调用 Umi-OCR，落库、落文件 | 唯一允许调用 Umi-OCR 的角色 |
| Umi 客户端 | 封装 Umi-OCR 的全部 HTTP 调用、重试、超时 | 全系统唯一出口，可被测试替身替换 |
| Umi 进程托管 | 启动/健康检查/崩溃重启 Umi-OCR.exe | 不修改 Umi-OCR 的配置，只做进程级管理 |
| 仓库层 | SQLite 读写，隐藏 SQL | 其他模块不写 SQL |

### 4.3 关键取舍记录

| 决策 | 选择 | 备选 | 理由 |
| --- | --- | --- | --- |
| PDF 处理方式 | 整份交给 Umi-OCR `/api/doc` | 后端拆页后逐张调 `/api/ocr` | 备选需引入 PDF 渲染库（Win7 上最易失败的 C 扩展）；本方案能直接产出双层可搜索 PDF |
| 进度推送 | 前端轮询（1s，仅活跃任务） | SSE 长连接 | cheroot 为线程模型，长连接白占线程；轮询穿透代理更稳 |
| 后端框架 | Flask 3.0 + cheroot 11.1.2 | FastAPI + uvicorn、Flask + waitress | 三者均无编译依赖。waitress 官方明确不支持 TLS，而摄像头要求 HTTPS，选它必须再加一层反向代理（Win7 上又多一个组件）；cheroot 原生支持 TLS 且报告真实客户端 IP，直接满足需求 |
| 图像处理位置 | 全部放浏览器 | 服务端生成缩略图 | 避免 Pillow 依赖；代价是 TIFF 等格式无法预览 |
| Umi-OCR 部署方式 | 由后端托管并仅监听 127.0.0.1 | 独立部署并允许局域网访问 | 其并发能力差，暴露到局域网会被多用户直接打崩且无鉴权 |

---

## 5. 技术选型与版本锁定

后端运行环境：**Python 3.8.10 x64**（官方最后一个支持 Win7 的版本）。

依赖全部为纯 Python 包，锁定版本：

```
Flask==3.0.3
Werkzeug==3.0.6
Jinja2==3.1.4
MarkupSafe==2.1.5
itsdangerous==2.2.0
click==8.1.7
blinker==1.8.2
cheroot==11.1.2
jaraco.functools==4.1.0
more-itertools==10.5.0
requests==2.31.0
urllib3==2.2.3
certifi==2024.8.30
idna==3.10
charset-normalizer==3.3.2
openpyxl==3.1.5
pytest==8.3.3        # 仅开发
```

选型说明：

- WSGI 服务器选 cheroot 而非 waitress：waitress 官方文档明确写"不支持 TLS"，而摄像头必须走 HTTPS；cheroot 原生支持 TLS 并报告真实客户端 IP，省掉反向代理。cheroot 11.1.2 要求 Python ≥ 3.8；其依赖 `jaraco.functools` 锁 4.1.0（4.2 起要求 3.9+）、`more-itertools` 锁 10.5.0（11 起要求 3.10+）。
- 不使用 SQLAlchemy，直接用标准库 `sqlite3`，减少版本耦合。
- 不使用 Pillow / OpenCV / pypdfium2 / PyMuPDF 等任何含 C 扩展的库。
- 密码哈希用标准库 `hashlib.scrypt`，不引入 bcrypt / argon2。
- 前端 `pdfjs-dist@3.11.174` 本地打包（不用 4.x，其对浏览器版本要求更高），不使用 CDN。

---

## 6. Umi-OCR 集成

### 6.1 使用的接口

| 接口 | 方法 | 用途 |
| --- | --- | --- |
| `/api/ocr/get_options` | GET | 健康探测；拉取图片识别参数定义供前端生成设置界面 |
| `/api/ocr` | POST | 图片识别（base64 入，同步返回） |
| `/api/doc/get_options` | GET | 拉取文档识别参数定义 |
| `/api/doc/upload` | POST | 上传 PDF，返回任务 ID |
| `/api/doc/result` | POST | 轮询任务状态与页数进度，任务结束后取文本 |
| `/api/doc/download` | POST | 生成并获取产物下载链接（双层 PDF / txt / csv / jsonl） |
| `/api/doc/clear/<id>` | GET | 清理任务与其临时文件 |

### 6.2 进程托管

- 服务启动时若探测不到 Umi-OCR，则按配置路径启动 `Umi-OCR.exe`（隐藏窗口）。
- 健康检查：周期性 GET `/api/ocr/get_options`，连续 3 次失败判定为不可用并尝试重启。
- 重启策略：最多连续重启 5 次，之后停止自动重启并在系统状态页与日志中告警，需人工介入。
- 不修改 Umi-OCR 的配置文件。若探测失败且进程存在，提示管理员在其"全局设置 → 高级"中确认已允许 HTTP 服务、主机为"仅本地"、端口与配置一致。

### 6.3 图片项执行流程

1. 读取原始文件 → base64 编码（无 `data:` 前缀）。
2. `POST /api/ocr`，请求体 `{"base64": ..., "options": {...}}`，其中 `options` 含语言、`tbpu.parser`、忽略区域等，来自任务创建时的设置。
3. 判定结果：`code==100` 成功；`code==101` 记为"无文字"；其余记为失败并保存 `data` 中的原因。
4. 文本写入结果文件并更新数据库。

### 6.4 文档（PDF）项执行流程

1. `POST /api/doc/upload`（multipart：`file` + `json` 选项字符串）→ 取得 `umi_task_id`。
2. 轮询 `POST /api/doc/result`（`is_data=false`），间隔 1 秒，更新 `page_done / page_total` 并回写数据库（供前端显示页级进度）。
3. `is_done` 为真后：
   - `state=="success"`：再以 `is_data=true, format="text"` 取回文本；
   - `state=="failure"`：记为失败，保存 `message`；同时以 `is_data=true` 再取一次，若存在部分结果则一并保存。
4. 若任务需要双层可搜索 PDF：`POST /api/doc/download`（`file_types:["pdfLayered"]`）取得下载链接，由后端下载保存到结果目录。**必须在 clear 之前完成**。
5. `GET /api/doc/clear/<umi_task_id>` 清理，放在 `finally` 中保证执行。

### 6.5 重试、超时与清理

- 判为"连接类故障"（连接被拒、超时、5xx）时退避重试 3 次：1s / 3s / 9s；仍失败则记为失败。
- 判为"业务类故障"（PDF 加密且未提供密码、参数非法、`code` 为业务错误码）不重试，直接失败。
- 超时：图片单项 120 秒；PDF 单项 `max(300, page_total × 20)` 秒，上限 7200 秒。
- 增量超时：PDF 轮询若无任何进度变化超过 600 秒，判为卡死，终止并记为失败。
- 所有 Umi 任务在本次执行结束时清理，避免 24 小时缓存堆积。

---

## 7. 数据模型

SQLite，开启 WAL 与 `busy_timeout=5000`；每个线程持有独立连接。所有时间以 UTC ISO8601 字符串存储。

```sql
users(
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  display_name TEXT,
  password_hash TEXT NOT NULL,          -- scrypt$n$r$p$salt_b64$hash_b64
  role TEXT NOT NULL DEFAULT 'user',    -- user | admin
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  last_login_at TEXT
);

jobs(
  id TEXT PRIMARY KEY,                  -- uuid4 hex
  user_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  source_type TEXT NOT NULL,            -- image | pdf | camera | mixed
  status TEXT NOT NULL,                 -- draft|queued|running|done|partial|failed|canceled
  ocr_options TEXT NOT NULL,            -- JSON
  item_total INTEGER NOT NULL DEFAULT 0,
  item_done INTEGER NOT NULL DEFAULT 0,
  item_failed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);

job_items(
  id TEXT PRIMARY KEY,                  -- uuid4 hex
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL,                   -- image | pdf
  source TEXT NOT NULL,                 -- upload | camera
  original_name TEXT NOT NULL,
  stored_relpath TEXT NOT NULL,         -- 相对 data/uploads 的路径，文件名用 uuid
  byte_size INTEGER NOT NULL,
  status TEXT NOT NULL,                 -- queued|running|done|empty|failed|skipped
  umi_task_id TEXT,
  page_total INTEGER,
  page_done INTEGER,
  text_relpath TEXT,
  artifact_relpaths TEXT,               -- JSON，如 {"pdfLayered": "..."}
  char_count INTEGER,
  preview TEXT,                         -- 前 200 字，供列表展示
  error_code TEXT,
  error_message TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  queued_at TEXT, started_at TEXT, finished_at TEXT,
  duration_ms INTEGER
);

settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);

audit_log(
  id INTEGER PRIMARY KEY,
  user_id INTEGER,
  action TEXT NOT NULL,
  target TEXT,
  detail TEXT,
  ip TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_items_job ON job_items(job_id, seq);
CREATE INDEX idx_items_status ON job_items(status, queued_at);
CREATE INDEX idx_jobs_user ON jobs(user_id, created_at DESC);
CREATE INDEX idx_jobs_status ON jobs(status);
```

文件布局：

```
data/
  ocr.db
  uploads/<job_id>/<uuid>.<ext>        原始上传文件
  results/<job_id>/<uuid>.txt          识别文本
  results/<job_id>/<uuid>.pdf          Umi 生成的双层可搜索 PDF
  exports/<job_id>/<name>.<ext>        导出的合并文件（按需生成）
  certs/ca.crt ca.key server.crt server.key ca.cer
  logs/app-YYYY-MM-DD.log
  tmp/                                 请求级临时文件
```

---

## 8. 队列与调度

持久化真相在 `job_items.status`，内存中的队列只是视图，重启即重建。

调度规则：

1. 就绪集合 = `status='queued'` 且所属任务为 `running` 的项。
2. 按用户分组、组内按 `queued_at` 升序；调度器在用户之间轮转取项（round-robin），保证任一用户的大批量任务不会独占工作线程。
3. 取到项后立即在数据库内置为 `running`（含 `started_at`），避免多线程重复领取。
4. 工作线程数由配置 `ocr_workers` 决定，默认 1（与 Umi-OCR 的单实例并发能力匹配），可提到 2–4。

状态流转：

```
job:  draft ──start──▶ queued ──▶ running ──┬──▶ done      全部成功
                                            ├──▶ partial   部分成功、部分失败/无文字
                                            ├──▶ failed    全部失败
                                            └──▶ canceled  人工取消
item: queued ──▶ running ──┬──▶ done    识别成功
                           ├──▶ empty   无文字
                           └──▶ failed  失败（含原因）
      未开始的项在任务取消时置为 skipped
```

崩溃恢复：服务启动时把所有 `running` 的项重置为 `queued`，`attempts + 1`；对应 `job.status` 由 `running` 回到 `queued`。

取消：取消任务时，未开始的项置 `skipped`；正在执行的项允许跑完当前项，PDF 任务额外调用 `/api/doc/clear` 强行终止。

---

## 9. 后端 API 契约

统一响应：成功 `{"ok": true, "data": ...}`；失败 `{"ok": false, "error": {"code": "...", "message": "..."}}`，并附合适的 HTTP 状态码。

错误码：`auth_required` `forbidden` `not_found` `invalid_request` `payload_too_large` `unsupported_type` `disk_low` `umi_unavailable` `conflict` `rate_limited` `invalid_credentials` `internal`。

认证（除登录外均需会话）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | `{username, password}` → 会话 Cookie + CSRF token |
| POST | `/api/auth/logout` | 注销 |
| GET | `/api/auth/me` | 当前用户信息与角色 |
| POST | `/api/auth/password` | 修改自己的密码（需原密码） |

任务：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/jobs` | 建任务 `{title, source_type, ocr_options}` → `job_id` |
| POST | `/api/jobs/<id>/items` | multipart 单文件上传（一次一个文件）→ 项信息 |
| POST | `/api/jobs/<id>/start` | 提交入队 |
| GET | `/api/jobs` | 列表，参数 `page/page_size/status/mine/scope` |
| GET | `/api/jobs/summary` | 各状态计数，供顶部徽标 |
| GET | `/api/jobs/<id>` | 任务详情 |
| GET | `/api/jobs/<id>/items` | 分页列出项 |
| GET | `/api/jobs/<id>/events?since=<ts>` | 增量拉取变化的项状态与进度 |
| POST | `/api/jobs/<id>/cancel` | 取消 |
| POST | `/api/jobs/<id>/retry` | 重试失败项（可带 `item_ids`） |
| DELETE | `/api/jobs/<id>` | 删除任务（含文件） |

结果与产物：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/items/<id>/text` | 取识别文本（`text/plain; charset=utf-8`） |
| PUT | `/api/items/<id>/text` | 保存人工校对后的文本 |
| GET | `/api/items/<id>/preview` | 原始文件（用于预览，带鉴权） |
| GET | `/api/items/<id>/artifact?type=pdfLayered` | 下载产物 |
| GET | `/api/jobs/<id>/export?format=txt\|csv\|xlsx\|jsonl&scope=all\|success` | 导出合并结果 |

系统与管理：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/system/status` | 引擎在线状态、队列长度、工作线程数、磁盘余量、版本 |
| GET | `/api/system/ocr-options` | 代理 Umi 的参数定义（缓存 5 分钟） |
| GET | `/api/system/root-cert` | 下载根证书 `ca.cer`（无需登录，仅此一个文件公开） |
| GET/POST | `/api/users` | 用户列表 / 新建（管理员） |
| PATCH | `/api/users/<id>` | 改角色、启停、重置密码（管理员） |
| GET/PUT | `/api/settings` | 运行时设置读写（管理员） |
| POST | `/api/maintenance/cleanup` | 手动触发过期清理 |

约定：

- 上传接口单请求上限 `upload_max_mb`（默认 200MB），超出返回 `payload_too_large`。
- 所有写操作要求请求头 `X-CSRF-Token` 与会话中的 token 一致。
- 普通用户只能访问自己的任务与项；管理员可访问全部。
- 列表接口一律分页，默认 50 条。

---

## 10. 前端设计

页面：

1. 登录页：用户名、密码、错误提示、首次登录强制改密提示。
2. 工作台：三个导入入口 + 当前任务卡片列表 + 上传队列。
3. 任务列表：筛选（全部/我的/进行中/已完成/失败）、分页、批量操作（取消、重试、删除、导出）。
4. 任务详情：左侧文件/页面预览，右侧识别文本（可编辑、可复制、可下载），PDF 显示页级进度；顶部显示状态、耗时、操作按钮。
5. 系统状态：引擎状态、队列、磁盘、日志摘要（管理员）。
6. 设置：OCR 参数（由 `/api/system/ocr-options` 动态生成表单）、上传上限、保留天数、工作线程数（管理员）。

关键交互：

- 导入图片：`<input type=file multiple accept=image/*>` + 拖拽区 + 文件夹选择（`webkitdirectory`）。上传采用"先建任务、再逐文件上传"，每个文件独立请求并显示进度，失败可单独重传。
- 导入 PDF：多选，逐个上传，上传后立即显示页数（在识别开始时由 Umi 回报）。
- 拍照：`navigator.mediaDevices.getUserMedia` → `enumerateDevices` 选择设备 → 预览 → 拍摄到 canvas → 生成 JPEG Blob → 可裁剪旋转 → 加入任务。非安全上下文隐藏入口并给出 https 链接提示。
- 预览：图片直接展示；PDF 用本地打包的 pdf.js 渲染；不支持的格式显示占位。
- 结果：按需加载单项文本，支持一键复制全文、下载单项 txt。

前端工程：Vue 3 + `<script setup>` + Pinia（状态）+ 原生 fetch 封装（含 CSRF 与统一错误处理）；构建目标 `es2017`；路由用 hash 模式以避免服务端重写配置；构建产物由 Flask 托管。

---

## 11. 安全设计

- 会话：签名 Cookie（`HttpOnly`、`SameSite=Lax`、https 时加 `Secure`），密钥首次启动随机生成并保存到 `data/session.key`。
- 密码：`hashlib.scrypt`（n=16384, r=8, p=1）+ 每用户随机盐；不在日志中记录密码或哈希。
- CSRF：登录下发 token，前端存内存并在写请求头携带，后端与会话比对。
- 登录限速：同一用户名 + IP 连续失败 5 次锁定 5 分钟。
- 首个管理员：首次启动自动创建 `admin`，随机密码打印到控制台并写入 `data/initial_admin_password.txt`，登录后提示改密并删除该文件。
- 文件访问：一律通过数据库记录映射到磁盘路径，磁盘文件名使用 uuid；拼接路径前校验 `os.path.realpath` 仍在 `data/` 之内，防止路径穿越。
- 上传校验：扩展名白名单 + 文件头 magic bytes 校验（图片：JPEG/PNG/BMP/WEBP/TIFF/GIF；PDF：`%PDF-`）。
- 权限：普通用户只能访问自己的资源；管理员可跨用户访问并在审计日志留痕。
- 审计日志：登录、建任务、删除、导出、用户与设置变更均记录（用户、动作、目标、IP、时间）。
- 传输：同时提供 http 与 https；https 使用自签证书（根证书 + 服务器证书，SAN 写入服务器 IP 与主机名，可配置），根证书可通过 `/api/system/root-cert` 下载，附一键导入脚本与图文说明。

---

## 12. 配置项

来源优先级：环境变量 > `config.json` > 内置默认值。

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `host` | `0.0.0.0` | 监听地址 |
| `http_port` | `8080` | http 端口，设 0 可关闭 |
| `https_port` | `8443` | https 端口，设 0 可关闭 |
| `enable_https` | `true` | 是否启用 https |
| `cert_san` | 自动探测本机 IP | 证书 SAN 列表（额外主机名/IP 用逗号分隔） |
| `data_dir` | `./data` | 数据根目录 |
| `umi_exe_path` | `./vendor/umi-ocr/Umi-OCR.exe` | Umi-OCR 可执行文件路径 |
| `umi_host` / `umi_port` | `127.0.0.1` / `1224` | Umi-OCR 服务地址 |
| `umi_autostart` | `true` | 是否由后端启动 Umi-OCR |
| `ocr_workers` | `1` | 工作线程数 |
| `web_threads` | `8` | cheroot 每个监听的工作线程数 |
| `upload_max_mb` | `200` | 单文件上传上限 |
| `retention_days` | `90` | 结果与原始文件保留天数，0 表示不自动清理 |
| `disk_min_free_gb` | `5` | 低于该值拒绝新任务并告警 |
| `log_level` | `INFO` | 日志级别 |
| `session_secret_file` | `./data/session.key` | 会话密钥文件 |

---

## 13. 存储与保留

- 磁盘水位低于 `disk_min_free_gb` 时：拒绝创建新任务（返回 `disk_low`），系统状态页高亮告警。
- 每日定时清理：删除超过 `retention_days` 的任务，先删文件再删记录；被引用的导出文件一并清理。
- 任务完成后保留中间产物（原始文件、文本、双层 PDF）；用户手动删除任务时全部清理。
- Umi-OCR 侧临时任务在每次执行结束时立即清理，不依赖其 24 小时自动回收。

---

## 14. 错误处理与日志

- 分层：接口层做参数校验并返回结构化错误；工作线程的异常一律捕获并写入该项的 `error_code/error_message`，绝不让单个坏文件影响整批任务。
- 日志：按天滚动写入 `data/logs/`，同时输出到控制台；记录请求（方法、路径、用户、耗时、状态码）、任务流转、Umi 调用耗时与结果码、重试与重启事件。
- 系统状态页展示最近若干条错误摘要，便于管理员定位是引擎问题还是文件问题。
- Umi-OCR 进程输出（stdout/stderr）重定向到 `data/logs/umi-ocr.log`，便于排查引擎侧问题。

---

## 15. 目录结构

```
my-ocr/
├─ backend/
│  ├─ app.py                 应用装配、蓝图注册、静态资源
│  ├─ config.py              配置加载与校验
│  ├─ db.py                  连接管理、建表、迁移
│  ├─ security.py            密码哈希、会话、CSRF、限速
│  ├─ logging_setup.py       日志配置
│  ├─ umi/
│  │  ├─ client.py           Umi-OCR HTTP 客户端（唯一出口）
│  │  └─ manager.py          进程托管与健康检查
│  ├─ queue/
│  │  ├─ scheduler.py        轮转调度
│  │  └─ worker.py           执行单个任务项
│  ├─ repositories/
│  │  ├─ users.py  jobs.py  items.py  settings.py  audit.py
│  ├─ services/
│  │  ├─ ingest.py           上传接收与校验
│  │  ├─ export.py           导出 txt/csv/xlsx/jsonl
│  │  ├─ retention.py        保留策略与清理
│  │  └─ certs.py            自签证书生成
│  └─ api/
│     ├─ auth.py  jobs.py  items.py  system.py  users.py  settings.py
├─ frontend/
│  ├─ index.html  vite.config.ts  package.json
│  └─ src/{ main.ts, router, stores, api, views, components, utils }
├─ tests/
│  ├─ fake_umi.py            可控故障的假 Umi 服务
│  ├─ test_*.py
├─ tools/
│  ├─ gen_cert.ps1           证书生成
│  ├─ import_root_cert.bat   客户端导入根证书
│  ├─ build_offline_bundle.ps1  离线依赖包
│  ├─ run_server.bat         启动脚本
│  └─ register_service.ps1   开机自启（计划任务）
├─ docs/
│  ├─ deploy-win7.md  deploy-win10.md  user-guide.md  cert-guide.md
│  └─ superpowers/specs/2026-09-26-lan-offline-ocr-design.md
├─ data/                     运行时生成（不入库）
└─ vendor/                   Umi-OCR 与离线依赖包（不入库）
```

---

## 16. 测试策略

| 层次 | 手段 | 覆盖内容 |
| --- | --- | --- |
| 单元 | `tests/fake_umi.py` 作为可控的 Umi 替身 | 调度公平性、状态机流转、重试退避、崩溃恢复、超时判定、路径安全、导出格式 |
| 接口 | Flask test client + 假 Umi | 认证与权限、CSRF、上传校验、分页、增量事件 |
| 集成 | 真实 Umi-OCR + 真实文件 | 端到端冒烟：图片、加密 PDF、多页 PDF、无文字图片、损坏文件 |
| 前端 | Vitest + 假 `mediaDevices` | 上传队列、进度合并、拍照生成 Blob、裁剪参数 |
| 手工 | 验收清单 | Win7+Chrome109、Win10+Edge、macOS+Safari、Firefox；并发 3 用户同时提交 |

关键回归用例（必须稳定通过）：一个用户提交 200 张图片的同时，另一个用户提交 1 张图片，后者应在 30 秒内完成（验证轮转调度）；识别过程中杀掉 Umi-OCR 进程，任务应自动恢复并最终完成。

---

## 17. 部署与运维

Win7 SP1 x64 前置条件：安装 SP1 与 Universal C Runtime（KB2999226），安装 Python 3.8.10 x64。

步骤：

1. 复制发布包到服务机（含 `vendor/umi-ocr`、离线 wheels、后端代码、已构建的前端）。
2. 运行 `tools/build_offline_bundle.ps1`（联网机器上执行一次）生成依赖包；离线机用 `pip install --no-index` 安装。
3. 首次运行 `tools/run_server.bat`：创建数据目录、生成证书与会话密钥、创建管理员、启动 Umi-OCR、监听端口。
4. 运行防火墙放行脚本，放行 http/https 端口。
5. 用 `tools/register_service.ps1` 注册开机自启（计划任务，隐藏窗口；Win10 亦可）。
6. 各客户端访问 `http://server:8080`；需要拍照的客户端按 `cert-guide.md` 导入根证书后改用 `https://server:8443`（或直接一步到位用 https）。

运维要点：

- 备份 = 复制 `data/` 目录（含数据库与结果文件）；建议定期执行。
- 升级 = 停服务 → 替换代码 → 启动（数据库结构变更有迁移脚本）。
- 引擎升级：替换 `vendor/umi-ocr` 目录，重启服务；OCR 参数界面会自动跟随新版接口。
- 故障排查入口：`data/logs/app-*.log`、`data/logs/umi-ocr.log`、系统状态页。

---

## 18. 里程碑

| 里程碑 | 内容 | 验收标准 |
| --- | --- | --- |
| M1 骨架 | 工程结构、配置、数据库、认证登录、自签证书与 https、Umi 客户端与进程托管、系统状态页 | 浏览器能登录并看到引擎在线状态；https 下根证书可下载 |
| M2 图片批量 | 多选/拖拽/文件夹导入、队列调度、进度、结果查看与编辑、导出 txt/csv | 三用户并发提交图片任务互不阻塞；结果可编辑并导出 |
| M3 PDF 批量 | 上传、页级进度、双层可搜索 PDF 与文本产出、导出 | 100 页 PDF 正常完成并产出双层 PDF；加密 PDF 给出明确错误 |
| M4 拍照 | 设备选择、连拍、裁剪旋转、证书导入脚本与说明 | Win7+Chrome109 与 macOS+Safari 均能拍照并识别 |
| M5 收尾 | 用户管理、设置、历史检索、清理策略、Excel 导出、部署脚本与文档 | Win7 与 Win10 各完成一次全新安装部署验证 |

---

## 19. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| Win7 缺少 UCRT 导致 Python 无法运行 | 无法部署 | 部署文档列出补丁号并在启动脚本中做前置检查 |
| Umi-OCR 偶发连接被拒或崩溃 | 任务失败 | 退避重试 + 健康检查 + 自动重启，失败项可一键重试 |
| 大 PDF 长时间占用唯一工作线程 | 其他用户等待 | 用户轮转调度；工作线程数可配；页级进度可见 |
| 磁盘写满 | 全部任务失败 | 水位检查拒绝新任务 + 清理策略 + 状态页告警 |
| 自签证书在客户端不生效 | 摄像头不可用 | 提供导入脚本与图文说明；证书含 SAN；支持后续替换为内网 CA 证书 |
| 浏览器不支持 TIFF 预览 | 体验下降 | 列表显示占位与文件名，识别流程不受影响；后续可用可选组件补缩略图 |
| Python 3.8 生态逐步停止维护 | 后续依赖升级困难 | 锁定版本并把依赖打进离线包，运行期不需要联网解析依赖 |

---

## 20. 开放问题

暂无。规模量级与导出需求按第 2 节与第 12 节的默认值实施，后续按实际使用调整配置即可，不影响架构。
