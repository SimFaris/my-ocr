# 部署到 Windows 10 / 11

步骤与 [Windows 7 部署](deploy-win7.md) 基本一致，只有以下几点不同。

## 可以用更新的 Python

Win7 上限是 Python 3.8.10，Windows 10/11 没有这个限制。本项目已在 **Python 3.8.10** 与
**Python 3.14** 上跑通全部测试，因此：

- 想与 Win7 保持一致：装 Python 3.8.10，用 `requirements.txt` 锁定的版本；
- 想用新版本：装任意 3.9+ 的 64 位 Python，用 `requirements-dev.txt`（不锁版本）安装即可，
  实测 3.14 可用。

## 更推荐免安装运行时

在 Win10 上同样可以双击 `start_server.bat` 直接跑（先用 `tools\build_runtime38.ps1` 打包
`vendor\runtime38`）。这样服务机不依赖系统里的 Python，也避免误升级。

## 其他差异

- 不需要装 Universal C Runtime（系统自带）。
- 防火墙提示同样选择"允许访问"，或运行 `tools\firewall.ps1`。
- 计划任务注册方式相同（`tools\register_service.ps1`）。
- 客户端拍照同样需要 HTTPS 与导入根证书，见 [cert-guide.md](cert-guide.md)。

## 部署后自检清单

与 Win7 文档第六节一致。此外建议在 Win10 上额外确认一次"多用户并发"：两台客户端同时提交
图片任务，观察任务详情页的进度与系统状态页的工作线程状态。