# 通用模式晋级候选：[模式名称]

> 本模板只用于目标无关、脱敏、可由 fixture 或回归测试复现的通用模式。项目日志、目标身份/路径、源码或二进制事实、凭据、IDB 和 session trace 禁止写入本仓库。

## 抽象问题形状

- 适用 target kind：
- 通用触发条件：
- 非目标专属的失败模式：
- 明确不适用范围：

## 最小方法

1. `<step one>`
2. `<step two>`
3. `<step three>`

## 可复现证据

- 离线 fixture：
- 回归测试与精确命令：
- 期望 success oracle：
- 工具/协议版本边界：

## 脱敏与来源检查

- [ ] 不含项目名、目标名、域名、IP、本机路径或凭据
- [ ] 不含目标源码/二进制事实、IDB、截图或运行 trace
- [ ] 方法可由合成 fixture 或公开规范独立解释
- [ ] `anonymization.md` 检查通过

## 进化分层

- [ ] `candidate`：证据不足，只能提示
- [ ] `validated`：oracle 与回归通过，可进入 promotion review
- [ ] `forensic`：失败/异常分析，不参与控制流

## Promotion record

- 关联 regression：
- 关联 oracle：
- review 结论：
- rollback 条件：

只有显式 promotion gate 通过后，才能更新 `routing.json`、`routing.md`、child skill、AIGX 或 capability manifest。不得自动更新 `_index.md` 或创建项目日志。
