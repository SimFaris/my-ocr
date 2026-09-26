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
| M2 | 批量导入图片：多选/拖拽/文件夹、任务队列与轮转调度、进度、结果查看与编辑、导出 txt/csv | 待开发 |
| M3 | 批量导入 PDF：页级进度、双层可搜索 PDF 与文本产出、导出 | 待开发 |
| M4 | 摄像头拍照：设备选择、连拍、裁剪旋转、证书导入引导 | 待开发 |
| M5 | 用户管理、参数设置、历史检索、清理策略、Excel 导出、部署脚本与离线依赖包 | 待开发 |

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

# 3) 生成自签证书（首次）
.\.venv\Scripts\python.exe tools\gen_cert.py

# 4) 启动（同时监听 http 8080 与 https 8443）
.\.venv\Scripts\python.exe run.py
```

首次启动会自动创建管理员账号，并把随机初始密码写入
`data/initial_admin_password.txt`；登录后请立即改密码，改密成功该文件会自动删除。

浏览器访问 `http://<服务器IP>:8080`。需要用摄像头时改走 `https://<服务器IP>:8443`，
并先导入根证书：访问 `https://<服务器IP>:8443/api/system/root-cert` 下载，或在客户端
以管理员身份运行 `tools\import_root_cert.bat`。

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