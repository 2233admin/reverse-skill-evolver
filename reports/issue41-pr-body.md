关联 #41（PowerShell 工具发现与失败处理）。

复用已推送的原提交 `632cf1af9371083ce90dca294e161b549ed83168`，未重写提交或实现。共享工具定义和安装入口，修复 PowerShell 5.1 JSON 兼容、Frida 原生 CLI 枚举/暂停参数、Java/JAR 可用性、无 adb 打包、引导/SSH/SCP 失败退出码；保留公开参数与索引字段。

本轮将精确 Git commit 的只读 archive 解到本专属 worktree 内临时目录，运行 `python -m pytest tests/test_powershell_scripts.py tests/test_bootstrap_contract.py tests/test_routing_contract.py -q --tb=short`：**39 passed，67.75 秒，退出码 0**，PowerShell 5.1/7 均执行。未改旧工作区或宿主配置，临时 snapshot 仅服务本次复验。

原提交的报告包含完整 Python 检查 256 passed、5 skipped，以及元数据查询五轮性能数据；这些是原提交已有证据。本轮没有重跑全套或性能测量，不将它们表述为新实测。性能数据只代表工具定义查询。

未验证：真实安装/下载、Android 设备操作、Frida 注入、远端同步。外部命令是隔离替身，不声称真实集成通过。此 PR 保持 Draft，下一责任人审阅者，合并需明确授权。
