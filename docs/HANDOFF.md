# 项目交接说明（Handoff）

> 给"下次接手的人"（包括未来的自己）看的一页纸：现在到哪一步了、怎么跑起来、
> 哪些验证过、哪些没验证、踩过哪些坑。
> 生成时间：2026-09-26　当前版本：0.1.0

## 一、这是什么

一套**局域网内离线运行的多用户 OCR 系统**。服务机一台 Windows（优先 Win7 SP1 x64），
用户在任意系统的浏览器里访问，支持批量图片、批量 PDF、调用本机 USB 摄像头拍照三种输入，
识别能力复用开源软件 Umi-OCR。

- 仓库位置：`E:\CODE\my-ocr`
- 设计文档：`docs/superpowers/specs/2026-09-26-lan-offline-ocr-design.md`（架构、选型、数据模型、接口清单）
- 安装使用：`docs/install-and-usage.md`
- 部署细节：`docs/deploy-win7.md`、`docs/deploy-win10.md`
- 客户端证书：`docs/cert-guide.md`
- 用户手册：`docs/user-guide.md`

## 二、当前进度

五个里程碑全部完成，**111 项后端测试 + 13 项前端单元测试全部通过**，且在
**Python 3.14 与 Python 3.8.10（Win7 支持的最高版本）下都跑过**。

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| M1 | 骨架、配置、数据库、登录认证、自签证书与 HTTPS、Umi-OCR 客户端与进程托管、系统状态页 | 完成 |
| M2 | 图片批量导入、任务队列与跨用户轮转调度、结果查看与编辑、导出 txt/csv | 完成 |
| M3 | PDF 批量识别、页级进度、双层可搜索 PDF、导出（含打包 zip） | 完成 |
| M4 | 摄像头拍照（设备选择、连拍、旋转、裁剪）、HTTPS 与证书导入引导 | 完成 |
| M5 | 用户管理、运行时设置、历史检索、保留策略清理、Excel 导出、部署工具与文档 | 完成 |

M5 之后还补了几处（都是实际使用中暴露的）：

- `58bece5` 修改密码界面（原先只有接口没有界面）+ 命令行重置工具
- `96c417d` 管理页禁止对自己重置密码（误操作陷阱）
- `0efd440` 免安装运行时下 `import backend` 失败
- `be50afb` Windows 注册表把 `.js` 当 text/plain 导致前端白屏
- `e07bc7c` 管理员跨用户查看任务、任务记录提交人与来源 IP
- `11a197c` 表格操作按钮改为带间距的胶囊按钮

提交历史：`git log --oneline`（当前 18 次提交）。

## 三、最短启动路径

```powershell
cd E:\CODE\my-ocr
.\.venv\Scripts\python.exe run.py        # 开发机
# 或者双击 start_server.bat（会自动选自带的运行时并生成证书）
```

浏览器打开 `http://127.0.0.1:8080`。管理员账号 `admin`，密码在
`data\initial_admin_password.txt`（首次启动生成，改密后自动删除；忘了就用
`python tools\reset_admin.py --username admin` 重置）。

## 四、关键文件

| 位置 | 说明 |
| --- | --- |
| `run.py` | 启动入口（http 8080 + https 8443，cheroot） |
| `start_server.bat` | 一键启动（自检 → 生成证书 → 启动），GBK 编码 |
| `config.json` | 本机部署配置（不入库），模板 `config.example.json` |
| `backend/` | 服务端：api / queue / repositories / services / umi / utils |
| `frontend/` | Vue 3 + Vite，产物 `frontend/dist` 由后端托管 |
| `tools/` | 证书生成、自检、离线打包、免安装运行时、开机自启、防火墙、密码重置 |
| `tests/` | pytest，含可控故障的假 Umi 服务 `tests/fake_umi.py` |
| `data/` | 运行时数据：`ocr.db`、`uploads/`、`results/`、`exports/`、`certs/`、`logs/` |
| `vendor/` | Umi-OCR、免安装运行时（`runtime38`）、离线依赖轮子（不入库） |

## 五、验证状态

**已在真机验证**：

- 后端 111 项测试在 Python 3.14 与 3.8.10 下全部通过
- 真实 Umi-OCR 端到端：图片、**真实扫描件 PDF（用户自己的 3 份，12 页 25087 字等）**、
  构造的 100 页图片型 PDF（22 秒完成，产出有效双层 PDF）、模拟拍摄上传
- HTTPS：自签证书通过真实 TLS 校验；未信任时握手被拒、导入信任后登录/状态/根证书下载正常
- 免安装运行时（Python 3.8 嵌入式）直接启动服务、登录、引擎在线
- 3.8 依赖可完整离线下载安装
- 数据库从 v1 自动迁移到 v2（补来源字段、保留历史数据）

**尚未验证**（需要现场确认）：

- 在真实 Win7 机器上执行完整安装（本机是 Windows 10/11）。风险集中在
  Universal C Runtime 补丁与 Umi-OCR 自身在 Win7 的表现
- 真实摄像头拍摄的画面质量（拍摄链路本身已验证）
- 多客户端并发（逻辑层有调度公平性测试覆盖）

## 六、踩过的坑（重要，别再踩一遍）

1. **waitress 不支持 TLS** → 改用 cheroot（原生 TLS、纯 Python、报告真实客户端 IP）。
2. **自签证书缺 SKI/AKI** → OpenSSL 直接拒绝握手，`tools/gen_cert.py` 已补。
3. **Windows 注册表把 `.js` 登记成 `text/plain`** → 浏览器拒绝加载 ES 模块、页面白屏。
   后端显式注册 MIME 类型（`backend/app.py` 的 `register_mime_types`）。
4. **Umi-OCR 的启动器会派生真实主进程后自己退出** → 进程句柄失效；改用其自带的
   `--hide` / `--quit` 命令接口，并以 HTTP 探测判断在线状态。
5. **Umi-OCR 冷启动需要若干秒** → 启动后必须轮询等待，否则会被误判为"重启失败"并耗尽重启次数。
6. **cheroot 默认开启 SO_REUSEADDR** → Windows 上两个实例能绑同一端口、请求被旧实例接走
   （表现为"改了代码没生效"）。启动入口现在会先检查端口占用。
7. **嵌入式 Python 是隔离模式** → `sys.path` 不含脚本目录，`run.py` 里必须显式加入项目根目录。
8. **改数组/导出时的大小写**：`format=pdfLayered` 会被转小写，比较时要注意。
9. `.bat` 文件用 **GBK(936)** 保存，中文才能在中文控制台正常显示；编辑时保持 GBK + CRLF。

## 七、怎么自检

```powershell
# 开发环境
.\.venv\Scripts\python.exe -m pytest

# 发布包里的免安装运行时（考到目标机后同样适用）
vendor\runtime38\python.exe -m pytest

# 前端
cd frontend; npm run test:unit

# 启动前环境自检（端口、目录、引擎路径、前端产物）
.\.venv\Scripts\python.exe tools\check_env.py
```

## 八、遗留与可选的下一步

- **M4/M5 里没做的**：识别参数的忽略区域（页眉页脚）还没有可视化框选界面；
  用户只能通过引擎默认参数识别后在结果里手工删。
- **可选增强**：Windows 局域网内用 `nbtstat -A` 兜底反查客户端机器名（目前只做 DNS 反查）。
- **可选增强**：全文检索（目前只检索入库的文本开头前 200 字 + 文件名）。
- **可选增强**：把 `ocr_workers` 提到 2–4 提升吞吐（需实测 Umi-OCR 的拒连概率）。
- **运维**：定期备份 `data` 目录即可（数据库、原始文件、结果、证书都在里面）。

## 九、本次开发的环境说明

开发期间 Codex 的**沙箱辅助进程故障**（`helper_unknown_error: setup refresh had errors`），
导致 `apply_patch` 与沙箱内命令全部不可用，所有改动都是通过沙箱外命令 + 脚本写文件完成的。
如果下次接手时遇到同样的报错，**重启 Codex 应用**即可恢复；恢复后应回到正常的编辑方式。