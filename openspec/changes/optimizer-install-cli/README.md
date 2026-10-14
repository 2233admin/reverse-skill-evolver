# 安装恢复与本地 CLI 修复

## 目的与范围

交付 [#56](https://github.com/2233admin/reverse-skill-evolver/issues/56) 的九项修复；父级 [#55](https://github.com/2233admin/reverse-skill-evolver/issues/55) 负责三组整合。仅修改远端清单和本目录/专属报告，不修改其他组、全局配置、共享文档、版本或 Release。

## 状态

待结项，2026-10-14；实现和验证已完成，Draft PR 交付及远端回读后停止本次执行。完整测试有两个范围外旧夹具失败，不表示整体验收通过。

分支：`2233admin/fix-optimizer-install-cli-20261014`

记录粒度：暂停时记录

## 批准记录

用户明确授权修复 #56、测试、提交、推送自己的分支、创建 Draft PR、写回 issue 并置工作区 in-review；远端 issue 保存同一授权及精确派发绑定。不新增实现批准门。

## 进度

九项已实现；384 项相关回归、gates all 和 OpenSpec 严格校验通过；全量测试 789 通过、2 失败、5 跳过，详见报告。下一步由父级分配旧 JAR 夹具更新的所有权，独立审查并整合 PR；本执行者不合并或发布。

## 要更新的现状文档

无共享现状文档写入授权。行为由生产代码和回归测试维护，实施依据及验证保存在本目录和专属报告。

## 推翻了以前的什么

安装发现不再把不完整托管 JAR 当作可用；原“最终文件存在即可”的判断是 #56 明确要求修复的缺陷。其他公开 CLI/output-v1、路由与授权承诺保留。

## 本目录的文档

- `proposal.md`：授权、问题和范围。
- `design.md`：实现选择和范围外夹具缺口。
- `tasks.md`：本次交付进度。
- `specs/optimizer-install-cli/spec.md`：验收场景。
- `evidence.py`、`evidence-results.json`：可重跑的基线/实现局部对照及原始样本。
- [专属验证报告](../../../reports/optimizer-install-cli-2026-10-14.md)：逐 ID 结果、检查、失败与未测边界。
