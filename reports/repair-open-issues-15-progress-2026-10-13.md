# 15 项接续修复记录

执行者：新 Session，单 Session 串行。工作区 `D:/projects/reverse-skill-evolver/repair-open-issues-15`，专属分支 `2233admin/repair-open-issues-15`，起点 `53010b3`。已核对 origin、Orca worktreeId、identity 和终端，均与交接文件一致；原 Session 已结束交接，无重叠写入。只写本工作区和专属分支，不操作其他工作区。

当前授权：2026-10-13 用户要求实际修复全部 15 项，验证、提交、推送并关联原 Issue/可审查 PR。此授权覆盖旧 Issue 的上一阶段“仅建单”说明。未获得本批全部 PR 的合并授权。Code Intel 在交接时已因缺少 DAG registry 不可用，依主机规则使用限定源码检查。

| Issue | 本轮状态 | 证据 / 下一步 |
| --- | --- | --- |
| #40 | 已推送 b0d78e9，Draft PR #42 | [交付回执](https://github.com/2233admin/reverse-skill-evolver/issues/40#issuecomment-6144184603)，未合并 |
| #33 | 修复并验证，交付同一 Draft PR #42 | 显式 open 超时，见下方；接续 #34 |
| #34 | 待实施 | 离线 doctor 诊断 |
| #35 | 待实施 | Burp bridge 和工具失败 |
| #36 | 待实施 | evolve 预算、进度、中断 |
| #37 | 待实施 | start 端口与根 URL |
| #38 | 待实施 | 经验索引编码与引用 |
| #39 | 待实施 | 首次上手文档，依赖前述行为 |
| #32 | 总览，待逐项回收 | 不视为独立代码修复，不提前关闭 |
| #41 | 已有提交待形成 PR | 复用 `632cf1a`，不重写 |
| #27–#30 | 已有 Draft PR #31，待功能验证 | 依赖 Draft PR #26；复用实现 |
| #21 | 待恢复有限真实模型预算 | 无预算不进行模型调用，推进独立项 |

## #40 验证

改动：移除进程名批量清理；Windows 按目标端口核实监听者 executable，持有 process handle 后核对再停止。归属不明/检查失败保留进程并诊断；健康端口始终复用。每次启动保存独立日志，返回 PID/logPath；提前退出报告实际退出码和日志尾；readiness 使用单调时钟截止，超时保留当前子进程供用户检查。

实际运行：`python -m pytest tests/test_ida.py tests/test_cli.py -q` → **55 passed**。包括真实隔离 Python 监听进程的两端口保护/未知归属保留，以及真实子进程退出码 17/stderr 保留、0.5 秒超时及日志/PID 检查。

完整回归：`python -m pytest -q` → **234 passed, 5 skipped**；`git diff --check` 通过。跳过项是现有可选集成/工具链检查，不能替代真实 IDA 验证。

未运行：真实 IDA 启动、替换他人服务。原因：本项以隔离进程验证生命周期和清理安全，不操作未核实归属的共享服务。未验证真实 IDA 许可证或二进制分析行为。日志保存在系统临时目录，由本次启动独立创建；超时后进程保持运行，恢复前须检查报告的 PID 和日志。

下一责任人：本 Session 交付 Draft PR 并继续 #33；PR 保持 Draft 待独立审阅和明确合并授权。

## #33 验证

根因与修复：`open` 将根超时限制为 30 秒，现直接传递 `state.timeout`，保留默认 120 秒、工具输出、异常传播和会话句柄。CLI contract 增加 600 秒示例。

实际运行：`python -m pytest tests/test_cli.py -q` → **50 passed**；`git diff --check` 通过。参数化检查默认 120、显式 600、短值 0.5，均通过公开 CLI 到达 MCP client；同一路径的超时仍返回退出码 4、单 JSON 错误、无成功会话且只调用一次。

未运行：真实复杂 IDA 样本的 600 秒分析。此项证明参数与错误合同，不证明真实分析完成。下一责任人：审阅者审阅 Draft PR #42；本 Session 接续 #34。
