# PR #42 查询异常的诊断顺序修正

根会话在用户确认 ready、处理反馈后合并及验收收尾之后刷新审阅，发现 [绑定 34fea04 的新意见](https://github.com/2233admin/reverse-skill-evolver/pull/42#pullrequestreview-5505287376)。原修复 session 已退出，其终端 disconnected/not writable；根会话接管干净的修复分支和本批整合，其他源码未被并行写入。

可复现行为：codex_registration 抛 OSError 或 UnicodeError 后，status/doctor 仍构造 MCP client 并请求 tools/list。强化原八项公开 CLI 回归（两命令、两输出、两异常），在旧实现均失败：8 failed/62 deselected，0.28 秒，实际记录 construct/request 两个边界调用。

修正只覆盖上述两个内部异常：保留本机 IDA 诊断与原异常/退出码 1，MCP 阶段标 unknown、online=null、checked=false，明确未执行且给出修复后重试动作，在构造 MCP client 前退出。正常未注册、缺安装、注册超时等既有独立 MCP 诊断流程保持原行为，没有扩大“所有诊断失败均不探测”的政策。

| 结论 | 验证方式 | 结果与局限 |
|---|---|---|
| 查询异常后没有 MCP 副作用 | 原八项 status/doctor human/JSON 回归计数构造和请求 | 新检查均通过；同时核对已发现 IDA 保留、未知状态、JSON 内部错误和退出码 1。外部边界为替身，不连接服务。 |
| CLI、JSON 合同和正常 MCP 路径保持 | `python -m pytest tests/test_cli.py tests/test_contract.py tests/test_mcp.py -q -p no:cacheprovider --tb=short` | 92 passed，17.14 秒，退出码 0；包括原缺安装/未注册/注册超时/健康路径。 |
| 变更范围 | diff 和工作区检查 | 仅 CLI 共享诊断入口、原八项行为断言和本说明。没有模型、配置、安装或服务操作。 |

本次授权来自当前会话用户“确认，现在能合并了吗”，对应根会话此前明确提出的三个 PR 转正式、处理反馈后合并、按验收条件收口；不是把 Agent 的 GitHub 评论误当用户批准。既有预验收和组合回归仅对未变源码复用；当前 head 的 CI/新反馈仍须在合并前回读。
