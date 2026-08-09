# Kali AIGX-first 启动桥

Kali 与其他平台共享仓库根目录的 AIGX genome、确定性 router 和 child skills。本文件只说明 Kali 入口，不复制路由规则。

1. 回到仓库根目录，读取 `.aigx/protocol.aigx` 与 `RULES.md`。
2. 使用官方 AIGX validator 验证项目 genome 与每个已知编辑边界。
3. 调用 `python skills/scripts/route_task.py --task "<task>" ...` 建立 route。
4. `status=blocked|invalid|no_route` 时不得执行；仅在 `status=ready` 时进入所选 child skill。
5. Kali 工具发现与安装仍使用 `kali/scripts/refresh-tool-index.sh`、`kali/scripts/bootstrap-reverse.sh` 及其 manifest，但只有当前 route 和用户授权允许时才执行有副作用的步骤。

不要把本文件写入 `~/.claude`、Kiro、Cursor、Cline、Windsurf 或其他客户端的全局配置。目标路径、凭据、运行证据和项目专属 Rules of Engagement 必须留在仓库外的当前 session 工作面。
