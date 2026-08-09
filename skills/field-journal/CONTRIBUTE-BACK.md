# 通用模式贡献合同

贡献不是任务结束时的自动步骤。运行 trace、目标证据与项目日志必须留在仓库外；只有目标无关、脱敏、具备离线 fixture/回归证据的通用模式，才可以被提议进入本仓库。

## 必须同时满足

- 当前内容不含项目名、目标身份/路径、源码或二进制事实、凭据、IDB、截图或 session trace。
- `_template.md` 的脱敏、fixture、oracle、版本边界与 rollback 项已填写。
- `candidate` 只提供建议；只有经 review 的 `validated` 模式可影响稳定路由。
- AIGX 官方 lint、相关回归、完整脚本测试与敏感数据扫描均通过。
- 用户对 commit、push、PR 等外部可见动作逐项给出当前授权。

## 审查顺序

1. 在仓库外把运行证据抽象为通用问题形状。
2. 用合成 fixture 或公开规范重建可复现证据。
3. 运行 `anonymization.md` 检查，并人工确认没有目标数据。
4. 写入 `candidate/` 或 `validated/` 草案，附 promotion record。
5. 只读 reviewer 核对边界、回归、oracle 与 rollback。
6. 只有显式批准后，才执行 commit、push 或 PR；不得自动合并。

任何检查失败时，保留外部运行证据并停止晋级，不得用模糊脱敏、占位符替换或新 baseline 掩盖问题。
