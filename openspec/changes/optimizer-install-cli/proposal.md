# 修复安装恢复并减少本地 CLI 开销

关联 [#56](https://github.com/2233admin/reverse-skill-evolver/issues/56)，父级 [#55](https://github.com/2233admin/reverse-skill-evolver/issues/55)。基线为 `d6d085364508215d0019b83f32dc58dd8f170c9e`；远端标题、bug/ready-for-agent 标签、原生父子关系及专用分支绑定已回读匹配。

用户已授权实现、测试、提交、推送专用分支和一个 Draft PR。本文保存本次实施依据，不增加批准门。

## 范围

仅处理 ER-02、ER-03、IO-01、DATA-03、SEC-01、ALG-04、DEAD-01、BUNDLE-01、BUILD-001。生产及测试路径遵循 #56 清单；本变更目录和 `reports/optimizer-install-cli-2026-10-14.md` 独占。其他两个执行组、主目录脏状态、共享 README/配置/CI/版本号均不修改。

## 结果

- 安装器显式传播失败；JAR 在独占兄弟文件完成验证后原子发布，遗留半成品可在下次调用修复。
- 每次索引刷新复用一次工具快照；fleet 使用忽略大小写的集合查找，保留遍历顺序。
- 邮件扫描每个候选局部串只尝试一次，报告在原文本定位边界，路由每次 plan 只准备一次任务文本。
- CLI 本地入口延迟导入 HTTP 客户端；共享输出和 ASR kinds 有独立轻量模块。
- launcher 在同一隔离子进程内检查导入并 dispatch；只允许明确的 dispatch 前导入失败触发一次修复。

## 验证与交付

关键失败先复现，使用无网络模拟安装、合成 Java JAR、隔离 Python 子进程和冻结路由数据验证。性能记录只做本机局部对照，不加时长断言、不宣称全产品加速。完成 Draft PR 后在 #56 记录 PR/head/证据，并将工作区置 in-review；审查、集成和发布归父级。
