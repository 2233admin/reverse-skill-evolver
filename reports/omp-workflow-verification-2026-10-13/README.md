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
