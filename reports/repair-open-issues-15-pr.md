关联 #40、#33；总览关联 #32。

Windows 上 `start --replace-stale` 原先按进程名清理所有 IDA MCP 服务，会打断其他端口。现在仅检查所选端口的监听者，持有进程 handle 后核实 executable 再停止；未知归属保留并返回检查命令，健康服务继续复用。

本次启动保留 stdout/stderr，返回 PID 和日志路径。提前退出报告实际退出码和日志尾；启动 readiness 使用单调时钟截止。超时保留子进程供检查，恢复前需检查报告的 PID 和日志。

验证：`python -m pytest tests/test_ida.py tests/test_cli.py -q`：55 passed；`python -m pytest -q`：234 passed, 5 skipped；`git diff --check` 通过。实际创建隔离 Python 监听进程验证两端口、未知归属和清理范围，创建隔离子进程验证 stderr/退出码 17、半秒超时和 PID/日志。

未运行真实 IDA 服务启动、替换共享服务、许可证和真实样本分析。此 PR 保持 Draft，等待独立审阅和明确合并授权。当前用户授权覆盖本轮修复、测试、提交、推送和 Draft PR，覆盖 Issue 上上一阶段“仅建单”说明。

接续进度与验证边界见 [修复记录](reports/repair-open-issues-15-progress-2026-10-13.md)。本批单 Session 在专属 worktree/分支串行交付，每项独立提交。

`open` 现在直接传递根 `--timeout`，默认 120 秒、显式 600 秒和短值 0.5 均经公开 CLI 验证。超时维持退出码 4、单 JSON 错误，不自动重试或产生成功会话。`python -m pytest tests/test_cli.py -q`：50 passed；未运行真实复杂样本分析。
