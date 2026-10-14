# optimizer-mcp-omp

状态：实现与本地验证已完成，随 #58 的 Draft PR 审阅；独立验收和集成由父级 #55 负责。

## 授权与范围

用户在 #55/#58 明确授权修复、测试、提交、推送自己的分支及一个 Draft PR；本事项没有实施前的新批准门。授权针对 MEM-02、ER-01、CONC-001、SEC-03、MEM-03，保留 issue 的路径所有权和公共契约边界。具体实现版本以 PR 的 Git 历史为准；本记录不把用户授权实施说成已逐份审阅或已验收。

## 记录入口

- [proposal.md](proposal.md)：问题、授权范围和交付边界。
- [design.md](design.md)：同步 MCP 的取消、原生 helper 所有权、匹配进程、回调锁与前缀快照选择。
- [tasks.md](tasks.md)：实现、验证和远端交付步骤。
- [specs/optimizer-mcp-omp/spec.md](specs/optimizer-mcp-omp/spec.md)：五项行为验收场景。
- [证据报告](../../../reports/optimizer-mcp-omp-2026-10-14.md)：改前改后对照、检查结果、失败和未验证边界。

## 当前判断

修复进入可审查状态；真实 IDA/Burp/OMP 集成、独立审查、跨 PR 集成和发布均不由本记录宣称完成。Code Intel 的缺失 DAG registry 已有失败记录，本事项沿用该事实并做有界读取，没有重跑全仓发现。
