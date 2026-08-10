# AIGX-first 路由启动桥

本仓库使用 AIGX 作为强制上下文平面。`.aigx/` 是项目规则与逐文件边界的唯一规范来源；本文件只提供中文兼容入口。

1. 先读取 `.aigx/protocol.aigx`，再读取当前任务涉及的 concern。
2. 项目任务运行 `reverse-skill context <项目根目录> --target <仓库相对路径>`；缺 genome、lint 失败或边界未解析都必须阻断。
3. 运行 `reverse-skill route <任务> --project-path <项目根目录> --aigx-target <仓库相对路径>` 构建确定性 route。
4. 只有 route 为 `ready` 时，才读取 `skills/SKILL.md`、所选 child skill 与当前能力证据；执行入口仍需显式 `--execute`。
5. IDA 插件和 Teams 状态分别使用 `reverse-skill plugins inventory` 与 `reverse-skill teams preflight <仓库>`；未显式传 `--ida-dir` 时自动选择本机最新可用 IDA。

不得因为读取本包而写入客户端全局配置、安装依赖或运行兼容 PowerShell 脚本。IDA 登录或安装必须保留为明确的用户交互动作。Session 角色、worktree、凭据、可变证据和目标身份都留在仓库外的运行时工作面。
