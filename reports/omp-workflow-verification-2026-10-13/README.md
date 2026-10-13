# OMP #27–#30 接续验证

本 Session 在专属 `2233admin/repair-open-issues-15` 分支复用 PR #26/#31 的原始 Git lineage（本地 merge 2362964），保留本轮 UX 修复及配置边界，不写原分支、不合入 main。旧静态/语法证据不替代本轮功能验证。合并后常规检查 **266 passed, 5 skipped**。

## #27 快照与初筛

实际编译两个自制 x64 PE DLL（toy-v1.c/toy-v2.c），包含导出 verify/check_license、decode_payload、已知 `license-invalid` 字符串、GetCurrentProcessId 导入与指向字符串的非函数数据引用。编译器为本机 LLVM clang/lld，链接固定本机 Windows SDK kernel32.lib；DLL 文件及输入 SHA 随报告保留。

使用本工作区局部 Python 3.13.15 环境，ida-domain 0.5.1、idapro 0.0.11、packaging 26.3、typing-extensions 4.16.0；本机 IDA Professional 9.4。通过 [OMP 固定 worker 源码](https://github.com/can1357/oh-my-pi/blob/fa5ff4a3a977a28b93d025f4cf50f046e019f18c/packages/coding-agent/src/ida/worker.py) 的真实 NDJSON open/exec 协议采集，源码 SHA-256 `07ebb0596badd8ba91a3dc122cf45149018323db7359ae3238c376e07e514fd1`。这直接运行生产 worker/真实 native helpers，未替换模型响应或 SDK 数据。worker 的输入、数据库文件与生命周期均在本 worktree 内自建范围；未动他人 IDB 或服务。

实际 native cases：两个版本均发现指定字符串/导入/函数候选；源 SHA 与实际 DLL 一致，EA/RVA 对应；空 regex 匹配保持 candidates=[]；非函数数据 xref 被跳过并计数；函数/字符串/导入/字节/pseudocode/xref/候选预算截断保持可见。正常分析可取得真伪代码，受限报告不冒充完整结果。保存完整 JSON 的示例实际执行，避免 native helper 的 DeprecationWarning 混进打印输出。

代码缺口修复：缺少 native namespace 原先只报 KeyError(db)，现给出“打开本任务原生数据库并传 exec globals”的明确错误；空/错误 metadata 原先可被 str() 伪装为来源，现拒绝。`python -m pytest tests/test_omp_analysis.py tests/test_omp_skill_contract.py -q --tb=short` → **22 passed**；包括预算、非函数 xref、无匹配、missing environment、来源校验和 assembly fallback。真实 native cases 在最终源码后重跑；原始 frames、stderr、完整 snapshot/triage/受限报告随附。

边界：这些是自制 x64 Windows 样本、固定 worker/SDK 的功能证据，不证明全部架构、任意二进制或实际用户场景。worker 不持有 OMP host registry ID，报告的 database_id 是调用方显式绑定的本地测试标识；其绑定可由输入路径/SHA/worker open frame核对，不能冒充 host registry 验证。自动分析创建本任务数据库；collector 没有调用 rename/comment/patch 等编辑 helper。模型调用 **0**（本批 #21 的 31 次独立保持）。

## 接续

#28 将消费这两个完整快照作实际对照；#29 用自制目标进程验证生成脚本；#30 执行本地 signer 样本和持久 eval 能力验证。各项单独补实际结果、提交推送及 Issue 回执，PR 保持 Draft。

## #28 跨版本对照

实际通过 CLI 消费 snapshot-v1/snapshot-v2。v1 的 verify_license 与 v2 的 check_license 名字和 RVA 均变化，使用显式一对一 mapping-v1-v2.json；decode_payload 使用两边唯一符号名对应。comparison-v1-v2.json 实际产生 2 个对应，记录 user_mapping/unique_symbol_name、字段变化及未匹配 padding_function。相同 RVA 不自动映射；未匹配观察不宣称新增/删除。没有符号迁移或 IDB 写操作。

复用 comparator 源码，未发现需要重写的运行缺陷。新增 17 项有意义回归，连同 collector **31 passed**：重命名/布局、重复名字、自动名称、相同 RVA、部分字节 hash/截断 coverage、assembly fallback 与未采集、架构/位数/格式/来源/RVA 错误、映射冲突、重复 JSON 字段/NaN、CLI 新建输出/拒绝覆盖/拒绝输入 alias。输入对象/文件内容保持不变。`git diff --check` 通过。

边界：真实 native 输入来自上述自制 x64 PE；人工构造错误 snapshot 属隔离负例，不冒充真实损坏数据库。函数对应/哈希差异是观察，非语义等价/漏洞证明。模型调用 0。下一项为 #29。

## #29 Frida 动态计划

修复模块名校验未拒绝 DEL (0x7f) 控制字符的缺口。`python -m pytest tests/test_omp_hook_plan.py tests/test_omp_skill_contract.py -q --tb=short` → **24 passed**；含 source/EA/RVA/ISA、模块名/重复目标、参数/事件/时限预算、计划 status/preconditions 保留与输入不变。

实际执行生成脚本：Frida **17.9.3**，只附加 `run-frida.py` 自己创建、载入已冻结 toy-v1.dll 的 Python 子进程。**7 cases PASS**，原 plan 和事件在 hook-plan-*.json、frida-verification.json：

- 正常运行验证真实 runtime module base 不等于静态 image_base，enter address 精确为 `module.base + RVA`，事件上限 2 后停止。
- 另一张独立伴随监听器在计划停止后仍收到调用，验证只 detach 自己的 listener。
- 未触发时限到期 events=0，保持未命中，不报告已验证假设。
- 错模块、错误位数、错误架构、超出模块范围、非可执行地址均在 setup_failed 时停止，events=0。后四类 artifact 为刻意故障注入，未冒充实际采集到的错误架构。

环境失败：第一次真实 attach 因默认 C 盘临时区域不足报 No space left on device；读数 C 剩余约 10 MB。只把本轮 driver 的 TEMP/TMP/TMPDIR 指向本 worktree `.verification/frida-temp` 后成功；未清理 C 盘、他人文件或修改宿主环境变量。异步伴随消息使用有界 Event 等待，避免消息尚未送达时误判 listener 已被清理。

生成的 plan 仍是 planned_not_run、identity/trigger preconditions 仍 unverified；本次运行事实单独记录，不改变生成器产品边界或宣称一般目标/假设已验证。实际 runtime 文件 SHA 与静态源匹配由 driver 独立核对；脚本不自动读指针内存。进程由创建者 stdin EOF 退出，session 只属于本任务，没有附加/关闭其他目标。模型调用 0。下一项为 #30。

## #30 签名复现与真实持久 eval

实际缺陷：自定义 Array 子类迭代器与 Proxy ownKeys trap 原先能在 fixture 校验时执行代码。现使用 Node 标准 types.isProxy 在反射前拒绝 Proxy，并限制数组为标准 Array prototype；原普通 JSON/callback 合同保持。

`node --test tests/omp-signature-replay.test.mjs` 与 `bun test tests/omp-signature-replay.test.mjs` 各 **9 passed, 0 failed**。覆盖同步/异步 HMAC signer、固定输入指纹、匹配/不匹配、异常隐私/非字符串、调用方/输入变更隔离、部分/空覆盖、字符串只作数据、重复 ID/expected/callback/budgets、非有限 JSON/循环/稀疏/符号/隐藏/访问器，以及两项新修复。Python 常规入口也执行 Node suite，与 portable skill 合同检查合计 **9 passed**。

真实 OMP **18.8.9** 已发现该 skill，并通过仅开放 eval 的一轮 MiniMax 会话执行 **3 个真实 js eval 调用**：导入/读取当前模块，定义 signer/fixtures/token，随后在同一持久 kernel 复用这些变量并调用 compareSignatures 两次。实际输出 `omp-persistent-replay.json`，完整固定 HMAC 用例 **2/2、passed=true**；maxCases=1 的部分报告 processed=1/remaining=1/complete=false/passed=false。预期 HMAC 由 driver 的 Python hmac 独立计算，实际签名由 JS signer 计算；原 tool_execution frames 显示模块调用/变量复用，没有靠模型叙述或替换预期构造通过。

这轮 OMP 会话耗时 **9.501 秒**，逻辑 OMP invocation **1**；加 #21 路由 31 次，全批累计 **32/37**。工具型一轮可能包含多个模型响应/重试，物理 provider 请求与账单仍未知，不把一次进程写成一次物理请求。输入是已标明的自制固定 HMAC fixtures，不是第三方真实捕获请求；没有新鲜服务器验收、业务认证/性能结论或模型候选晋级。

运行环境诊断：C 盘空间不足也阻止 OMP native addon 缓存解包；使用上游支持的 `PI_NATIVES_DIR` 指向本 worktree，再用私有 PI_CODING_AGENT_DIR 与进程 TEMP/TMP 运行。没有清理共享缓存/目录或修改宿主变量。API key 只来自进程环境并注入该次 CLI，不进入报告/Git；原始输出凭据扫描通过。
