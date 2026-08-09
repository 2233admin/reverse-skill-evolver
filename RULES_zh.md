# AIGX-first 路由启动桥

本仓库使用 AIGX 作为强制上下文平面。`.aigx/` 是项目规则与逐文件边界的唯一规范来源；本文件只提供中文兼容入口。

1. 先读取 `.aigx/protocol.aigx`，再读取协议要求的 concerns。
2. 运行官方 AIGX validator；若 lint 失败，立即停止。
3. 对每个已知编辑目标执行官方 `--resolve`；缺少边界时立即停止。
4. 通过 `skills/scripts/route_task.py` 构建确定性 route，并满足输入、能力、服务、授权和项目 gate。
5. 只有 `status=ready` 时，才能读取所选 child skill 并执行返回的受控入口。

不得把本文件或路由规则写入客户端全局配置，也不得在本通用仓库中保存目标身份、路径、凭据或分析证据。Session 角色、worktree、可变证据和收敛状态应保存在仓库外的运行时工作面。
