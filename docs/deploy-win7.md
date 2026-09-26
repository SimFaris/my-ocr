# 部署到 Windows 7 SP1 x64

本文档面向**服务机**的部署。客户端不需要安装任何东西，用浏览器访问即可（拍照功能需一次性导入根证书，见 [cert-guide.md](cert-guide.md)）。

## 一、前置条件

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 7 **SP1 x64**（必须是 64 位；本项目在 64 位系统上验证） |
| 系统补丁 | Universal C Runtime（KB2999226）。多数已打全补丁的机器自带；缺它时 Python 会报缺少 api-ms-win-crt-*.dll |
| 磁盘 | 建议预留 20 GB 以上（原始文件 + 识别结果 + 双层 PDF） |
| 网络 | 服务机与客户端在同一局域网；服务机本身不需要外网 |
| Umi-OCR | v2.1.4 以上（PDF 识别需要），官方声明支持 Win7 x64 |

## 二、选择部署方式

两种方式任选其一。**方式 A 不需要安装 Python**，在 Win7 上更省事，推荐。

### 方式 A：免安装运行时（推荐）

在**一台能上网的机器**上（可以是别的电脑，不一定是服务机）：

```powershell
# 1) 准备开发环境（仅打包时需要）
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 2) 构建前端产物
cd frontend
npm install
npm run build
cd ..

# 3) 打包免安装运行时（Python 3.8.10 嵌入式 + 全部依赖）
powershell -ExecutionPolicy Bypass -File tools\build_runtime38.ps1
```

然后把**整个项目目录**（包含 `vendor\runtime38`、`frontend\dist`、`vendor\umi-ocr`）拷到服务机。

### 方式 B：安装官方 Python + 离线依赖包

1. 在服务机上安装 **Python 3.8.10 x64**（python.org 最后一个支持 Win7 的版本；安装时勾选 Add Python to PATH）。
2. 在联网机器上生成离线依赖包：

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_offline_bundle.ps1
```

3. 把项目目录（含 `vendor\offline`）拷到服务机，运行 `vendor\offline\install_offline.bat` 完成依赖安装。

## 三、放置 Umi-OCR

把 Umi-OCR 解压到项目下的 `vendor\umi-ocr\`，并让配置文件指向实际的 exe：

```
vendor\umi-ocr\Umi-OCR_Rapid_v2.1.5\Umi-OCR.exe      ← Rapid 版（兼容性优先，默认用这个）
vendor\umi-ocr\Umi-OCR_Paddle_v2.1.5\Umi-OCR.exe     ← Paddle 版（速度稍快，可选）
```

`config.json`（不入库，模板见 `config.example.json`）：

```json
{ "umi_exe_path": "vendor/umi-ocr/Umi-OCR_Rapid_v2.1.5/Umi-OCR.exe" }
```

首次也可以在 Umi-OCR 界面里确认一次：全局设置（勾上"高级"）→ 允许 HTTP 服务、主机 **仅本地**、端口 **1224**。之后由本服务托管启停（启动时自动隐藏窗口）。

## 四、启动与初始化

1. 双击 `start_server.bat`。首次运行会自动：
   - 运行环境自检（Python、数据目录、端口、Umi-OCR 路径、前端产物）
   - 生成自签证书到 `data\certs`
   - 创建管理员账号，随机密码写入 `data\initial_admin_password.txt`
   - 启动 Umi-OCR 并监听 http 8080 / https 8443
2. 浏览器打开 `http://服务机IP:8080`，用 `admin` 与文件中的初始密码登录，**立即修改密码**（改完该文件会自动删除）。
3. 若弹出防火墙提示，选择"允许访问"；也可以管理员身份运行 `tools\firewall.ps1` 直接放行。

## 五、设为开机自启（可选）

以管理员身份运行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\register_service.ps1
```

会创建一个开机启动的计划任务（静默、不弹窗口）。取消：`tools\unregister_service.ps1`。

## 六、部署后自检清单

- [ ] 系统状态页显示"OCR 引擎：在线"
- [ ] 工作台导入一张图片，任务详情页能看到识别文本
- [ ] 导入一个扫描件 PDF，页级进度推进到底并产出双层 PDF
- [ ] 需要拍照的客户端：按 [cert-guide.md](cert-guide.md) 导入根证书后，用 https 打开并成功调起摄像头
- [ ] 多台客户端同时提交任务，互不阻塞
- [ ] 重启服务后，未完成的任务自动继续

## 七、常见问题

**启动时提示缺少 api-ms-win-crt-*.dll**
缺少 Universal C Runtime，安装 KB2999226（或改用方式 A 的免安装运行时）。

**启动时报"以下端口已被占用"**
上一个服务实例还在运行。关掉旧窗口，或在任务管理器结束残留的 `python.exe`。
注意 cheroot 默认开启 SO_REUSEADDR，Windows 上两个实例能绑同一端口、请求被旧实例接走，
所以启动入口会主动检查并拒绝启动。

**状态页显示"引擎不可用"**
检查 `vendor\umi-ocr\...\Umi-OCR.exe` 是否存在、`config.json` 里的路径是否一致；
再手工启动一次 Umi-OCR 确认它的 HTTP 服务已开启。服务会自动重启引擎，连续 5 次失败后会停止
自动重启并在状态页提示，需要人工介入。

**日志在哪**
`data\logs\app.log`（服务日志）、`data\logs\umi-ocr.log`（引擎输出）。

**如何备份**
复制整个 `data` 目录即可（数据库、原始文件、识别结果、证书全在里面）。

## 八、已验证与未验证的范围

已经在本机真机验证：

- 后端 99 项测试在 **Python 3.8.10**（Win7 支持的最高版本）下全部通过；同一套测试在 Python 3.14 下也通过
- 依赖在 3.8 下可完整下载并离线安装（全部为纯 Python 轮子，无编译需求）
- HTTPS：自签证书可被标准客户端校验通过，登录、状态、根证书下载正常
- 图片、扫描 PDF（含 100 页）、模拟拍摄结果三类输入均识别成功，文本与图片内容逐字一致
- 任务队列跨用户轮转、重启后中断任务自动回队

**尚未在真实 Win7 机器上执行过完整安装**（本机是 Windows 10/11）。Win7 特有的风险点集中在
Universal C Runtime 与 Umi-OCR 自身，建议按第六节清单在目标机上逐项确认。