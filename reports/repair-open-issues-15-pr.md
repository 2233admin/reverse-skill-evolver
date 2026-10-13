关联 #40、#33、#34、#35、#36、#37、#38、#39、#21、#27、#28、#29、#30；总览关联 #32。

Windows 上 `start --replace-stale` 原先按进程名清理所有 IDA MCP 服务，会打断其他端口。现在仅检查所选端口的监听者，持有进程 handle 后核实 executable 再停止；未知归属保留并返回检查命令，健康服务继续复用。

本次启动保留 stdout/stderr，返回 PID 和日志路径。提前退出报告实际退出码和日志尾；启动 readiness 使用单调时钟截止。超时保留子进程供检查，恢复前需检查报告的 PID 和日志。

验证：`python -m pytest tests/test_ida.py tests/test_cli.py -q`：55 passed；`python -m pytest -q`：234 passed, 5 skipped；`git diff --check` 通过。实际创建隔离 Python 监听进程验证两端口、未知归属和清理范围，创建隔离子进程验证 stderr/退出码 17、半秒超时和 PID/日志。

未运行真实 IDA 服务启动、替换共享服务、许可证和真实样本分析。此 PR 保持 Draft，等待独立审阅和明确合并授权。当前用户授权覆盖本轮修复、测试、提交、推送和 Draft PR，覆盖 Issue 上上一阶段“仅建单”说明。

接续进度与验证边界见 [修复记录](reports/repair-open-issues-15-progress-2026-10-13.md)。本批单 Session 在专属 worktree/分支串行交付，每项独立提交。

`open` 现在直接传递根 `--timeout`，默认 120 秒、显式 600 秒和短值 0.5 均经公开 CLI 验证。超时维持退出码 4、单 JSON 错误，不自动重试或产生成功会话。`python -m pytest tests/test_cli.py -q`：50 passed；未运行真实复杂样本分析。

`doctor/status` 在离线时保留本地信息并给出三个阶段的恢复动作。失败 JSON 保持 v1 envelope、`data:null` 和原 error code，在 `error.message` 的 `Diagnostics: ` 后包含诊断 JSON；人工输出与 integrations 改为摘要及下一步。`python -m pytest tests/test_cli.py tests/test_contract.py -q`：64 passed；另以真实离线端口运行 doctor 检查本机发现、失败提示与退出码。未修改宿主配置或运行 IDA 分析。

Burp bridge 支持未加载工具时单次有界重取（并发共用、成功缓存），并准确传递操作 `isError:true`。连接、HTTP/JSON/形状错误保持协议错误和请求 ID。真实 Node stdio/loopback 后端检查 6 passed；已接入 Python 测试入口。未运行 Burp GUI，未改 Java/攻击语义。

evolve 明确完整用例集评估/反思预算及实际 fixture 数对应的逻辑调用上限；stderr 输出阶段进度。模型调用前冻结归档输入，逐次 checkpoint 原始响应；异常/中断保留 incomplete 归档、失败位置和已完成结果，保留 not_promoted，不将部分 suite 作为比较/晋级依据；错误归档失败也不掩盖原评估错误。相关 evolution/CLI/合同测试 160 passed。此项为模拟 OMP 检查，真实模型验证另归 #21。

#21 真实 OMP 验证使用用户的新 MiniMax API：完整 12-case baseline/curated 各 12/12（24 调用、84.473 秒），另以刻意失败的单例候选完成真实 reflection，curated 0/1 → proposal 1/1（4 调用、14.187 秒）。含默认 provider 402 失败和 Windows cwd cleanup 失败累计 31/37 调用，均有原始响应/冻结输入/哈希/失败位置/候选 lineage。顺带修复 Windows 临时目录被锁时 cleanup 掩盖响应的实际故障，真实隔离 cwd 锁及 evolution 检查 95 passed。全部 not_promoted；token/物理请求/费用 unknown。细节见 [真实记录](reports/omp-live-2026-10-13/README.md)。

`start --port` 与根 `--url` 的独立关系写入 help、两种 README、IDA skill 与 contract，非默认 24444 示例保持同一地址；现有语义不变。help/公开 CLI 隔离参数核对及合同测试 4 passed；未操作真实服务或宿主注册。

经验索引从可读 Git `070bf87` 恢复，后续 New API 条目由现存同日日志补齐；保留脱敏占位、27 引用身份和 17 种子，26 实际目标均存在（另 1 个是明确文件名示例）。UTF-8 双读取核对通过。后续新增先例段落缺可靠原文，保留其三个链接并标明加载顺序/授权措辞未恢复，未猜写授权或晋级经验。

中英文首页以现有本地 IDA 任务贯通输入、依赖、路由、命令、实际 session、证据和恢复；明确一次性接入/日常复用/维护、命名配置块的修改与恢复。RULES 与详细接入节同步，纯阅读不触发配置写入，默认项目入口，全局范围需明确授权，已批准配置不重复询问。双语命令相同/新链接核对/7 条隔离 CLI recipe 均通过，CLI/合同检查 66 passed。稳定路由/fixture 未改；没有真实用户计时测试或本 recipe 的真实 IDA 分析。

OMP 项复用原 Draft PR #26/#31 的原始 Git lineage（本分支本地 merge），不改其原分支或 main；入口冲突保留本轮 UX/配置边界。原 #26 的后端导航元数据也包含在该 lineage 内，不是 #21 模型候选晋级。合并后完整回归 266 passed, 5 skipped。

#27：两个自制 x64 PE DLL 通过 pinned 生产 OMP worker 的真实 IDA open/exec，快照/初筛验证已知字符串、导入、函数、无匹配、预算截断和非函数引用。补缺 native 环境的明确错误与来源字段校验；相关检查 22 passed。保存完整 JSON 的样例实际运行；[scoped report](reports/omp-workflow-verification-2026-10-13/README.md) 保留输入 DLL/源码、实际 frames、完整 snapshot/triage 与限制。模型调用 0；其他架构/任意输入/host registry 集成未验证。

#28：实际 CLI 消费真实两版 native 快照，验证变名/布局显式对应、唯一符号名与未匹配观察。复用 comparator，新增 17 项回归，连同 collector 31 passed；覆盖重复名字、截断、错误来源/架构、映射冲突和 CLI 拒绝覆盖等。没有 IDB/符号迁移或模型调用，不以匹配结果证明语义等价。

#29：拒绝模块名 DEL 控制字符，输入/portable skill 检查 24 passed；真实 Frida 17.9.3 在自制 Python/DLL 进程通过 7 场景，覆盖 ASLR、命中/未命中、事件上限、伴随 listener 保留、错误模块/架构/位数/地址/执行区。plan 仍 planned_not_run，观察另存。首次受 C 盘空间限制，改 driver 进程临时目录到本 worktree 后成功，未清理或改宿主配置。没有第三方目标/模型调用。

#30：校验前拒绝 Proxy/非标准数组，防止 fixture 自定义陷阱/迭代器执行。Node/Bun 各 9 passed；真实 OMP 18.8.9 的一轮 MiniMax 会话实际调用3个js eval cells并复用持久变量/模块。完整HMAC用例2/2，部分用例remaining=1不通过，独立Python oracle/工具frames核对；9.501秒、1次逻辑OMP调用，全批32/37，物理请求/费用unknown。输入为自制fixtures，不是第三方网络capture。缓存/临时目录限于本worktree进程环境，未清理宿主缓存/改配置。
