# 局域网离线 OCR 系统

内网离线运行的多用户 OCR 服务：一台 Windows 机器集中部署，用户用浏览器访问，
支持批量图片、批量 PDF 与网页调用本机 USB 摄像头。识别能力复用开源软件
[Umi-OCR](https://github.com/hiroi-sora/Umi-OCR)，本项目只做工程化封装。

完整设计见 [设计文档](docs/superpowers/specs/2026-09-26-lan-offline-ocr-design.md)。

## 架构

```
浏览器（任意系统）──http/https──▶ 本机后端（Python 3.8 / Flask / cheroot）
                                    │  队列 + SQLite + 文件存储 + 自签证书
                                    │  仅 127.0.0.1
                                    ▼
                              Umi-OCR.exe（HTTP 服务，端口 1224）
```

后端是唯一入口：Umi-OCR 由后端托管，不对局域网暴露（官方文档说明其并发能力差、
大批量连续调用会偶发拒连，因此所有识别请求都必须由后端串行调度）。

## 当前进度

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| M1 | 工程骨架、配置、数据库、登录认证、自签证书与 HTTPS、Umi-OCR 客户端与进程托管、系统状态页 | 已完成 |
| M2 | 批量导入图片：多选/拖拽/文件夹、任务队列与轮转调度、进度、结果查看与编辑、导出 txt/csv | 已完成 |
| M3 | 批量导入 PDF：页级进度、双层可搜索 PDF 与文本产出、导出 | 已完成 |
| M4 | 摄像头拍照：设备选择、连拍、裁剪旋转、证书导入引导 | 待开发 |
| M5 | 用户管理、参数设置、历史检索、清理策略、Excel 导出、部署脚本与离线依赖包 | 待开发 |

## Umi-OCR 的放置与切换引擎

服务机上的目录结构（`vendor/` 不入库）：

```
vendor/umi-ocr/
  Umi-OCR_Rapid_v2.1.5.7z.exe          官方原始安装包（留档，便于拷到离线机）
  Umi-OCR_Paddle_v2.1.5.7z.exe         官方原始安装包
  Umi-OCR_Rapid_v2.1.5/Umi-OCR.exe     解压后的 Rapid 版（默认使用，兼容性优先）
  Umi-OCR_Paddle_v2.1.5/Umi-OCR.exe    解压后的 Paddle 版（速度稍快，备用）
```

本机用 `config.json` 指定实际使用的那一个（该文件不入库，模板见 `config.example.json`）：

```json
{ "umi_exe_path": "vendor/umi-ocr/Umi-OCR_Rapid_v2.1.5/Umi-OCR.exe" }
```

切换引擎：把 `umi_exe_path` 改成 `vendor/umi-ocr/Umi-OCR_Paddle_v2.1.5/Umi-OCR.exe`，
重启服务即可，其余配置不用动。

两点实践结论（已在真机验证）：

- Umi-OCR 的启动器会派生真实主进程后自己退出，因此后端不依赖进程句柄判断状态，
  而是以 HTTP 探测为准，并用 Umi-OCR 自带的 `--hide`／`--quit` 命令接口控制窗口与关闭。
- **不同引擎的参数名并不一样**：Rapid 版上报的是 `ocr.angle`、`ocr.maxSideLen`，
  Paddle 版上报的是 `ocr.cls`、`ocr.limit_side_len`。所以识别参数界面必须由后端
  动态读取引擎自报的参数表来生成（`GET /api/system/ocr-options` 已按此实现），
  不能在代码里写死参数名。
## 快速开始（开发机）

```powershell
# 1) 后端依赖（开发机用较新 Python 即可；目标机是 3.8）
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 2) 前端依赖与构建（只需在有 Node 的机器上做一次）
cd frontend
npm install
npm run build
cd ..

# 3) 启动（双击 start_server.bat 亦可，它会自动生成证书）
.\start_server.bat
```

首次启动会自动创建管理员账号，并把随机初始密码写入
`data/initial_admin_password.txt`；登录后请立即改密码，改密成功该文件会自动删除。

浏览器访问 `http://<服务器IP>:8080`。需要用摄像头时改走 `https://<服务器IP>:8443`，
并先导入根证书：访问 `https://<服务器IP>:8443/api/system/root-cert` 下载，或在客户端
以管理员身份运行 `tools\import_root_cert.bat`。

## 启动脚本

根目录的 `start_server.bat` 是日常启动入口，双击即可：

1. 自检：Python 版本、数据目录是否可写、自签证书是否已生成、Umi-OCR 路径、
   前端产物是否已构建、http/https 端口是否被占用（由 `tools/check_env.py` 完成）。
   出现阻塞项（端口占用、目录不可写）会直接停下并给出提示。
2. 首次运行时自动生成自签证书。
3. 启动服务并打印日志；按 `Ctrl+C` 停止。

也可以带参数运行，例如只监听 http 并换端口：

```
start_server.bat --no-https --http-port 8088
```

> 说明：`.bat` 文件用 **GBK(936)** 编码保存，这样中文在不切换代码页的中文 Windows
> 控制台里能正常显示。编辑这些文件时请保持 GBK 编码与 CRLF 换行。
## 使用流程

1. **工作台**：选择图片（支持多选、拖拽、整个文件夹），可选识别语言与排版方案，
   点「开始导入并识别」——文件逐个上传并显示进度，上传完自动进入识别队列。
   PDF 任务：在工作台把来源切到「PDF 文档」，可多选 PDF，并可勾选「生成双层可搜索
   PDF」；识别时任务详情页会显示 `已识别页数 / 总页数`。
2. **任务列表**：查看进度、按状态筛选，可取消、重试失败项、删除任务。
3. **任务详情**：左侧文件列表显示每项状态与耗时，点击任一项可看原图、查看并校
   对识别文本、保存修改；顶部可导出全部或仅成功项的 txt / csv。

任务与任务项的调度是跨用户轮转的：某个人提交几百张图片时，其他人后交的任务不会
一直排在后面等。识别工作线程数由 `ocr_workers` 配置（默认 1，与 Umi-OCR 的并发
能力匹配）。

## 常用命令

```powershell
.\.venv\Scripts\python.exe -m pytest                 # 运行测试
.\.venv\Scripts\python.exe run.py --http-port 8088 --no-https   # 仅 http、换端口
.\.venv\Scripts\python.exe tools\gen_cert.py --force --san 192.168.1.10,ocr-server
```

## 目录说明

| 路径 | 说明 |
| --- | --- |
| `backend/` | 服务端：配置、数据库、认证、接口、Umi 集成、任务调度 |
| `frontend/` | Vue 3 + Vite 前端，构建产物由后端托管 |
| `tools/` | 证书生成、启动脚本、客户端根证书导入脚本 |
| `tests/` | pytest 测试，含可控故障的假 Umi 服务（`tests/fake_umi.py`） |
| `data/` | 运行时数据：数据库、上传文件、识别结果、证书、日志（不入库） |
| `docs/` | 设计文档与部署文档 |

## 部署到 Windows 7 的注意事项

- 目标机使用 **Python 3.8.10 x64**（官方最后一个支持 Win7 的版本），依赖按
  `requirements.txt` 锁定，全部为纯 Python 包，可离线安装。
- 需要先安装 Win7 SP1 与 Universal C Runtime（KB2999226）。
- `requirements.txt` 是给目标机的；开发机上装的较新版本仅用于本地开发，
  两者的行为差异会在 M2 开始时用 Python 3.8 环境做一次回归验证。
- 前端在部署包中直接使用构建好的 `frontend/dist`，目标机不需要安装 Node。

## 安全说明

- 密码使用标准库 `hashlib.scrypt` 加盐存储；会话为签名 Cookie，https 下自动加
  `Secure` 标记；写操作校验 `X-CSRF-Token`；登录失败 5 次锁定 5 分钟。
- `data/certs/ca.key` 与 `server.key` 为私钥，**不可外发**。
- 所有文件访问都通过数据库记录映射，磁盘文件名为 uuid，防止路径穿越。

## 常见问题

**页面白屏，控制台报 `Expected a JavaScript-or-Wasm module script but the server
responded with a MIME type of "text/plain"`。**
Windows 注册表把 `.js` 的 Content Type 登记成了 `text/plain`，Python 的 `mimetypes`
会照抄这个结果，浏览器于是拒绝加载 ES 模块。后端已显式注册前端资源类型
（`backend/app.py` 里的 `register_mime_types`），不需要改注册表。
改完代码后请在浏览器里按 `Ctrl+F5` 强制刷新一次，清掉此前缓存的错误响应。

**控制台出现 `chrome-extension://...` 报错、`No Listener: tabs:outgoing.message.ready`
或 `GET chrome-extension://invalid/ net::ERR_FAILED`。**
这些来自浏览器插件（常见于带助手类插件的 Chrome），与本系统无关。想确认的话，
用无痕窗口或禁用插件后访问一次即可。

**启动时报「以下端口已被占用」。**
通常是上一个服务实例还在运行。注意 cheroot 默认开启 `SO_REUSEADDR`，在 Windows 上
两个实例能绑同一端口、请求被旧实例接走，所以启动入口会主动检查并拒绝启动。
处理办法：关掉旧窗口，或在任务管理器里结束残留的 `python.exe`。