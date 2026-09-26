# 局域网离线 OCR 系统 —— 安装与使用说明

本说明面向两类人：

- **部署人员**：按第 1–5 节在服务机上装起来；
- **普通用户**：直接看第 6 节（也可单独打印 `docs/user-guide.md`）。

---

## 1. 系统是什么

一台 Windows 机器作为服务机集中运行，用户在**浏览器**里访问，无需在客户端安装任何软件。
三种输入方式：

| 方式 | 说明 |
| --- | --- |
| 批量图片 | 多选、拖拽、整文件夹导入 |
| 批量 PDF | 扫描件逐页识别，可产出**双层可搜索 PDF**（能复制、能检索） |
| 摄像头拍照 | 用浏览器调起用户本机的 USB 摄像头，可连拍、旋转、裁剪（**需 HTTPS**） |

识别引擎是开源的 [Umi-OCR](https://github.com/hiroi-sora/Umi-OCR)（v2.1.4 以上），
由本服务托管启停，不对外暴露。

## 2. 系统要求

**服务机**（推荐）：Windows 7 SP1 **x64** 或 Windows 10/11 x64，内存 4 GB 以上（8 GB 更稳），
磁盘预留 20 GB 以上。Win7 需要 Universal C Runtime（KB2999226），缺它时 Python 会报缺少
`api-ms-win-crt-*.dll`。

**客户端**：任意系统的近年浏览器——Chrome/Edge ≥ 90、Firefox ≥ 90、Safari ≥ 14。
Win7 上的上限是 Chrome/Edge 109、Firefox 115 ESR，均可正常使用（拍照也支持）。

**网络**：服务机与客户端在同一局域网。服务机本身**不需要外网**。

## 3. 部署（三选一）

### 方式 A：免安装运行时（推荐，服务机不用装 Python）

前提：拿到本项目目录，且其中已包含 `vendor\runtime38`（打包时由
`tools\build_runtime38.ps1` 生成）。直接跳到第 4 节。

如果手上没有 `vendor\runtime38`，在**一台能上网的机器**上执行：

```powershell
cd <项目目录>
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd frontend; npm install; npm run build; cd ..
powershell -ExecutionPolicy Bypass -File tools\build_runtime38.ps1
```

然后把**整个项目目录**拷到服务机。

### 方式 B：服务机自己装 Python

1. 在服务机安装 **Python 3.8.10 x64**（安装时勾选 Add Python to PATH）。
2. 把项目拷到服务机，运行：

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> 已经是 Win10/11 且想用更新的 Python 也可以（本项目在 3.14 上验证过），
> 这时用 `requirements-dev.txt`（不锁版本）安装。

### 方式 C：离线依赖包（服务机装了 Python 但没有外网）

在联网机器上执行 `tools\build_offline_bundle.ps1`，把生成的 `vendor\offline` 连同项目拷到服务机，
运行 `vendor\offline\install_offline.bat`。

## 4. 放置 Umi-OCR

把 Umi-OCR 解压到项目的 `vendor\umi-ocr\` 下，目录形如：

```
vendor\umi-ocr\Umi-OCR_Rapid_v2.1.5\Umi-OCR.exe      兼容性优先，默认用这个
vendor\umi-ocr\Umi-OCR_Paddle_v2.1.5\Umi-OCR.exe     速度稍快，可选
```

然后编辑项目根目录的 `config.json`（没有就复制 `config.example.json`）：

```json
{ "umi_exe_path": "vendor/umi-ocr/Umi-OCR_Rapid_v2.1.5/Umi-OCR.exe" }
```

首次也可以手工启动一次 Umi-OCR，在「全局设置（勾上高级）」里确认：**允许 HTTP 服务**已开、
主机为**仅本地**、端口 **1224**。之后由本服务负责启停。

## 5. 首次启动

双击 `start_server.bat`（或运行 `vendor\runtime38\python.exe run.py`）。它会：

1. 自检环境（Python、数据目录、端口占用、引擎路径、前端产物），有问题会直接提示；
2. 首次自动生成自签证书到 `data\certs`；
3. 创建管理员账号，随机密码写入 `data\initial_admin_password.txt`；
4. 启动 Umi-OCR（隐藏窗口）并监听 **http 8080 / https 8443**。

见到 `服务已启动：http://0.0.0.0:8080` 即成功。

**接下来必做两件事**：

1. 放行防火墙（首次可能弹提示，选"允许"；或管理员运行 `tools\firewall.ps1`）；
2. 浏览器打开 `http://服务机IP:8080`，用 `admin` 与初始密码登录，**点右上角「修改密码」改成自己的密码**。

需要开机自启：管理员运行 `tools\register_service.ps1`（取消用 `tools\unregister_service.ps1`）。

## 6. 日常使用

### 6.1 改密码

右上角「修改密码」：填当前密码 + 新密码（≥8 位）。忘记密码时让管理员在服务机上执行：

```
vendor\runtime38\python.exe tools\reset_admin.py --username 用户名
```

### 6.2 导入图片 / PDF

「工作台」→ 选择来源（图片 / PDF 文档）→ 选择或拖入文件 →（可选）调整识别参数 →
「开始导入并识别」。文件逐个上传并显示进度，上传完自动进入识别队列，页面跳到任务详情。

PDF 若勾选「生成双层可搜索 PDF」，识别完成后可下载带文字层的 PDF。

### 6.3 拍照

**必须先走 HTTPS**：浏览器规定只有安全上下文才允许调用摄像头。步骤：

1. 客户端访问 `http://服务机IP:8080/api/system/root-cert` 下载根证书（此接口不需要登录）；
2. 双击安装到「受信任的根证书颁发机构」（Windows）或钥匙串并设为「始终信任」（macOS）；
   也可用管理员身份运行 `tools\import_root_cert.bat`；
3. **重启浏览器**，改用 `https://服务机IP:8443` 打开系统；
4. 进「拍照」→ 允许摄像头权限 → 拍摄（可连拍）→ 需要时旋转/裁剪 → 开始识别。

详细步骤与排错见 `docs/cert-guide.md`。

### 6.4 查看与导出结果

任务详情页左侧是文件列表，点任一项看原图与识别文本：

- 直接改文本框内容 → 「保存校对结果」；
- 顶部可导出 **txt / csv / Excel**（全部或仅成功项）；PDF 任务还能导出**双层 PDF**（多个自动打包）。

### 6.5 检索历史

「检索」页按关键字查找任务标题、文件名与识别文本开头。要查完整正文，请导出该任务后再搜。

## 7. 管理员功能

- **范围切换**：「任务列表」与「检索」左上角可切换「全部用户 / 只看我的」。切到全部时，
  表格会多出**用户**与**来源**两列（来源 = 提交时的 IP + 尽力反查的机器名）。
  这两列只对管理员可见。
- **用户管理**（「管理」页）：新建用户、改角色、停用/启用、重置密码。
  自己那一行显示的是「改自己的密码」（避免误把自己锁在门外）。系统不提供删除用户，
  因为任务记录靠用户关联，停用是替代做法。
- **系统设置**：保留天数、磁盘水位、单文件上传上限、识别工作线程数、日志级别，
  改完**立即生效**并持久化，不需要重启。
- **立即清理**：手动执行一次保留策略（删除超过保留期的任务及其文件、清理无主目录）。

## 8. 备份、升级与排错

**备份**：直接复制整个 `data` 目录（数据库、原始文件、识别结果、证书、日志都在里面）。

**升级**：停服务 → 覆盖程序文件（保留 `data`、`config.json`、`vendor`）→ 再启动。
数据库结构变更会自动迁移，历史数据保留。

**查日志**：`data\logs\app.log`（服务）、`data\logs\umi-ocr.log`（引擎）。

**常见问题**：

| 现象 | 处理 |
| --- | --- |
| 启动提示"以下端口已被占用" | 上一个实例还在跑，关掉旧窗口或结束残留 `python.exe` |
| 状态页显示引擎"不可用" | 检查 `config.json` 里的 Umi-OCR 路径；手工启动一次确认 HTTP 服务已开 |
| 页面白屏、控制台报 MIME 类型不对 | 后端已显式注册 MIME；按下 `Ctrl+F5` 强制刷新 |
| 拍照页提示需要 HTTPS | 按 6.3 导入根证书并改用 https 访问 |
| 摄像头提示被占用 | 关掉系统相机应用、会议软件等占用摄像头的程序 |
| 忘记管理员密码 | `vendor\runtime38\python.exe tools\reset_admin.py --username admin` |
| Win7 报缺少 api-ms-win-crt-*.dll | 安装 Universal C Runtime（KB2999226） |

## 9. 已验证与未验证

**已验证**：后端 111 项测试在 Python 3.14 与 3.8.10 下全部通过；真实扫描件 PDF（12 页/6 页）、
100 页构造 PDF（22 秒完成并产出有效双层 PDF）、图片与拍摄上传均识别成功；HTTPS 通过真实
TLS 校验；免安装运行时可直接启动服务。

**未验证**：真实 Win7 机器上的完整安装（风险集中在 KB2999226 与 Umi-OCR 在 Win7 的表现）；
真实摄像头的拍摄画质；多客户端并发（逻辑层已覆盖调度公平性）。

部署后建议按 `docs/deploy-win7.md` 第六节的清单逐项确认。