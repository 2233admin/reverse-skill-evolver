# 通用先例与已晋级模式索引

> 本索引只列出 skill 包自身的通用、脱敏、已审查内容。不得记录目标身份、项目路径、session 运行证据或授权声明，也不得在任务结束时自动维护。

## 当前 Session 授权

- [`precedent-auth.md`](precedent-auth.md) — 说明 `authorization_scope` 的 fail-closed 合同；文件本身不授予权限。

## 通用方法先例

- [`precedent-reverse.md`](precedent-reverse.md) — 逆向工程方法参考。
- [`precedent-pentest.md`](precedent-pentest.md) — 渗透测试方法参考。
- `seed-001` 至 `seed-017` — 脱敏的固定方法样例，仅作离线参考。

## 进化层

- [`candidate/README.md`](candidate/README.md) — 未晋级候选，仅提供建议。
- [`validated/README.md`](validated/README.md) — 通过回归、脱敏与 review gate 的通用模式。
- [`forensic/README.md`](forensic/README.md) — 仅供分析的问题模式。

项目运行 trace、目标证据、凭据、IDB 和授权记录必须保存在本仓库外。只有不含目标数据、具备回归证据且经显式审查的通用模式，才能按 promotion gate 进入上述进化层。
