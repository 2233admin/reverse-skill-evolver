# 新 Session 交接：修复 15 张开放 Issue

## 当前用户目标与授权

用户最新原话：“不是还有15个工作 我们开一个新的session 用woktree去修复”。

用户要求的是在新的隔离 worktree 和全新 Codex session 中接续修复当前 15 张开放 Issue，实际修改代码、验证并交付。原 session 完成交接后停止重叠写入。你是此接续批次的执行者，单 Session 串行推进；用户没有要求额外并行启动 Agent。

此前用户要求“先把这些做成 issue，我们一个一个修”，随后确认修复方案。#32/#40 正文中的“本轮仅整理/建单，不开始修复”是上一阶段记录；当前用户已明确要求开始修复，不得把旧阶段说明当作阻止本次代码修复的条件。

当前授权覆盖这些 Issue 的代码、常规本地/隔离测试、必要文档、Git 提交、推送修复分支及创建可审查的 Draft PR。合并、关闭和真实模型消耗依照已有明确授权与适用流程；先完成可审查交付，不能用“可能需要许可”为理由停掉其他可独立执行的工作。

## 精确落点与所有权

- contractRepo / executionRepo：GitHub `2233admin/reverse-skill-evolver`，origin 为 `https://github.com/2233admin/reverse-skill-evolver.git`。
- Orca repoId：`45882e91-0419-434c-bcc4-8539dcf734f7`。
- worktreeId：`45882e91-0419-434c-bcc4-8539dcf734f7::D:/projects/reverse-skill-evolver/repair-open-issues-15`。
- worktree identity：`wt2:local:6f9a26de-a2df-442b-8fa8-f5fedc5d6c23`。
- 实际工作目录：`D:/projects/reverse-skill-evolver/repair-open-issues-15`。
- 初始分支：`refs/heads/2233admin/repair-open-issues-15`。
- 起始基线：`origin/main` = `53010b3d5591f78333062fe8056782ed769f4a7d`。
- 接收终端：`term_3d42700c-dd29-407e-bb69-63a1bc4c8552`。
- ownedPaths：此新 worktree 内、直接服务这些 Issue 的源代码、测试、文档及验证报告；Git 推送限于你专属的新修复分支，或经活动占用核验后明确接续的已有修复分支。
- delivery：逐项形成关联原 Issue 的实际提交、Draft PR 与可独立核验的验证证据；#32 是 UX 总览，按子项实际交付回写进度。
- 本批交接只创建这一份工作区与 Session，不创建监督 Run/Task，也不等待原 session 协调。

启动先核对 cwd、git remote、branch 和 Orca 身份。旧工作目录 `F:/projects/reverse-skill-evolver` 位于历史 Issue #4 分支，仍有其他人的报告/构建产物和这次已提交代码的工作区副本。只读参考它，不回退、不清理、不把其所有脏文件加入你的提交。不改其他 worktree、宿主配置或未核实归属的共享进程。

先读 `C:/Users/Administrator/AGENTS.md` 及当前任务触发的链接。主机 Code Intel 目前因缺少 DAG capability registry 失败；记录后按主机约定使用 bounded rg/直接源码检查，不把修复环境变成主任务。

## 当前 15 张开放 Issue

以下是交接时 GitHub 回读快照，实施前逐项重读正文、评论、依赖、已有 PR 和最新源码：

- [#41 [perf/reliability] 优化 PowerShell 工具发现与调用，修复兼容和失败处理](https://github.com/2233admin/reverse-skill-evolver/issues/41)
- [#40 [UX/P1] 限定 IDA 服务清理范围并保留启动失败诊断](https://github.com/2233admin/reverse-skill-evolver/issues/40)
- [#39 [UX/P2] 整合首次上手流程并明确接入配置边界](https://github.com/2233admin/reverse-skill-evolver/issues/39)
- [#38 [UX/P2] 恢复乱码的经验索引并核对引用](https://github.com/2233admin/reverse-skill-evolver/issues/38)
- [#37 [UX/P2] 说明 start 端口与根 URL 的使用关系](https://github.com/2233admin/reverse-skill-evolver/issues/37)
- [#36 [UX/P2] 明示 evolve 预算与进度并保留中断结果](https://github.com/2233admin/reverse-skill-evolver/issues/36)
- [#35 [UX/P1] 恢复 Burp bridge 连接并正确标记工具失败](https://github.com/2233admin/reverse-skill-evolver/issues/35)
- [#34 [UX/P1] 让 doctor 在离线时保留诊断并给出恢复动作](https://github.com/2233admin/reverse-skill-evolver/issues/34)
- [#33 [UX/P1] 保留 open 命令的显式超时设置](https://github.com/2233admin/reverse-skill-evolver/issues/33)
- [#32 [UX] 整合首次上手、诊断与故障恢复的逐项修复](https://github.com/2233admin/reverse-skill-evolver/issues/32)
- [#30 [feature] OMP 持久 eval 的 JS 签名样本复现](https://github.com/2233admin/reverse-skill-evolver/issues/30)
- [#29 [feature] OMP 静态线索到 Frida 动态验证计划](https://github.com/2233admin/reverse-skill-evolver/issues/29)
- [#28 [feature] OMP 跨版本快照对照与映射报告](https://github.com/2233admin/reverse-skill-evolver/issues/28)
- [#27 [feature] OMP 批量函数初筛与证据快照](https://github.com/2233admin/reverse-skill-evolver/issues/27)
- [#21 [test] Validate bounded routing evolution with live OMP responses](https://github.com/2233admin/reverse-skill-evolver/issues/21)

15 是开放 Issue 数，其中 #32 是总览，不是第九份独立 UX 代码修复。执行中状态变化以 GitHub 为准，不为了清零数量提前关闭票。

## 修复顺序和既有产物

### UX 主线

既定串行顺序：**#40 → #33 → #34 → #35 → #36 → #37 → #38 → #39**。先实际开始 #40“限定 IDA 服务清理范围并保留启动失败诊断”。

#40：现有 `reverse_skill/ida.py` 会按进程名 taskkill 全部同名服务，可能打断其他端口任务；启动 stdout/stderr 被丢弃，未观察子进程提前退出。修复只能处理当前目标且归属可核实的进程，保留健康复用、日志/PID/退出信息和有界失败。用隔离进程/命令记录覆盖多端口、归属不明、健康复用、提前退出和超时，避免操作其他人的真实 IDA 服务。具体验收以 Issue #40 最新正文为准。

#39 依赖 #33/#34/#35/#36/#37/#40 的最终行为，其他 UX 项没有人为硬依赖。#32 回写各子项的实际进展，不用测试总数替代逐条验收。

原 session 的可复用说明（只读）：
- `F:/projects/reverse-skill-evolver/reports/ux-issue-plan-2026-10-13.md`
- `F:/projects/reverse-skill-evolver/reports/ux-issue-receipt-2026-10-13.json`
- `F:/projects/reverse-skill-evolver/reports/autoplan-ux-2026-10-13.md`
- `F:/projects/reverse-skill-evolver/reports/autoplan-ux-receipt-2026-10-13.json`

这些是定位线索；远端 Issue 和用户本次授权优先。不要重新跑一套产品访谈或只交另一份计划。

### #41：复用已推送的 PowerShell 优化

已实现、提交、推送，**不要重写**：
- 分支：`origin/fix/issue-41-powershell-optimization`。
- 提交：`632cf1af9371083ce90dca294e161b549ed83168`。
- 8 个脚本 + 1 份测试 + 2 份报告，共 11 文件。
- 相关测试 39 passed（PowerShell 5.1 / 7）；在 main 基线上的完整 Python 检查 256 passed、5 skipped。
- 工具定义查询五轮、每轮 200 次，中位 233.85 ms → 82.78 ms；仅代表元数据查询开销。
- 尚无关联 PR，尚未合入 main；真实工具安装、设备操作、Frida 注入、远端同步未验证。
- 报告/原始数据已经在上述 commit 中；Issue #41 已链接提交与报告。

接续重点是复核当前 commit、形成关联 PR 和准确记录验证边界，不能从旧根目录 `git add .` 把其他报告/构建产物打包进来。该分支已有隔离 checkout `F:/projects/_worktrees/reverse-skill-evolver-issue41-powershell`，当前 clean；本次新 session 以自己 worktree 为主要写入范围。

### OMP 原有代码：#27–#30 与 Draft PR

- [PR #26](https://github.com/2233admin/reverse-skill-evolver/pull/26)：原生 IDA 基础支持，`feat/omp-ida-support`，head `caa6013938529cac4d668a249aebc9c80690371f`，base main `53010b3...`。Draft，未合入；已有本地/CI 与真实 toy binary 只读视图证据，零模型提示。
- [PR #31](https://github.com/2233admin/reverse-skill-evolver/pull/31)：四项工作流，对应 #27–#30，`feat/omp-analysis-workflows`，head `920e0dd972b0ace10a556bddfc04ef60e42fdc8e`，base 为 PR #26 的分支。Draft，未合入。
- #27 快照/函数初筛，#28 跨版本映射，#29 Frida 观察计划，#30 持久 eval 签名复现均已有代码。此前只做静态/语法核对，功能验收后置；现有 CI 成功不能当作这些新工作流已功能验收。
- 复用已有实现与合同，检查实际缺口、修复和补充适当验证；保留候选/计划/覆盖边界，不能把观察计划宣称为已注入结果。

### #21：真实 OMP 模型验证

远端记录：OMP 18.8.9 已安装，已完成配置/fixture 的无模型准备，实际模型调用为 0。Issue 明确要求有限预算；三个完整 12-case evaluation 加一次 reflection 的理论上限为 37 个逻辑 OMP 调用，provider 可能重试，因此不能把逻辑调用数伪称物理请求数。

先恢复是否已有用户批准的具体预算；缺少时完成无模型准备，待需要真实消耗时在新 session 提出一次具体的预算选择，并继续其他独立工作。不得把“修复15项”解释成无限模型预算，也不得把模拟结果标成真实验收。保持 `not_promoted`，不覆盖稳定路由/skills。

## 实施与交付要求

1. 每项开始前从 GitHub 恢复当前合同、依赖、评论决定和已有实现，检查是否被其他活动 session 占用；已完成的复用，不重复开票。
2. 优先最小完整修复，保持公开 CLI / JSON / 退出码合同。复用既有 helper，避免新增框架、GUI、安装器或无关配置。
3. 逐项运行能证明其验收条件的检查；报告实际运行/失败/跳过/未运行，隔离替身和真实运行分开。
4. 每项完成后独立提交、推送到专属分支，关联原 Issue，创建可审查 PR 和自足证据。用户已明确要求提交代码，不能只登记问题或把完成的改动留在工作区。
5. 一个受预算/实测条件限制的项不阻塞整个批次。证据不足就准确保留缺口，继续可独立推进的项。
6. 只对当前交付形成必要的 review/ready/merge/close 动作；遵守已明确授权及适用的 GitHub 交付/整合/生命周期技能。不把本次修复请求扩成无条件合并全部 PR。
7. 保存此交接文件，维护新 session 中可恢复的当前项、已交付项、待验证项与链接。不要用“测试全绿”替代其他 Issue 的需求验收。
8. 用简洁中文持续更新用户；现在先读 #40 并开始诊断/实现，不停在确认能力或再提一遍计划。

