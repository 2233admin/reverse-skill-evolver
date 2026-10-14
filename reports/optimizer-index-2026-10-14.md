# 索引资源保护与重复扫描修复验证

日期：2026-10-14。关联 [#57](https://github.com/2233admin/reverse-skill-evolver/issues/57)，父级 [#55](https://github.com/2233admin/reverse-skill-evolver/issues/55)。授权覆盖实施、验证、提交、推送及一个 Draft PR；本记录交独立审查，不代表父级集成或发布验收。

## 范围、来源与状态

基线为 `d6d085364508215d0019b83f32dc58dd8f170c9e`；分支为 `2233admin/fix-optimizer-index-20261014`。开始时回读远端正文、标签、评论、原生父级和 #55 子列表，确认 #57 是 `bug` + `ready-for-agent`、父级为 #55，执行仓库/工作区/分支/head/终端匹配且工作区干净、没有既有 PR。交付前远端 main 仍是该基线。

只改五个授权生产文件：`index_store.py`、`index_build.py`、`index_api.py`、`retrieval.py`、`ida_ingest.py`；新增 `tests/test_optimizer_index.py`，以及本 issue 专属 OpenSpec 和本报告。CLI、数据契约、共享 README、依赖、版本和其他组文件没有源改动。

审计来源为同机器的 `reverse-skill-evolver-optimizer-20261014` 只读备份中的 REPORT、reviewed-findings、database/algorithm/data/memory/security 专项及其 Python/JSON 证据。复制复现脚本到自己的 `.verification/optimizer-index/audit/` 后，仅修改副本的导入/产物位置并排除其他组实验；原审计产物和主目录已有脏状态未写入。沿用 Code Intel 缺 DAG registry 的既有失败，未重新做全仓发现。

## 每个 ID 的复现、修复与改善

这里的基线和修复后数据均为本次直接运行。正式原始收据为 [evidence-before.json](../openspec/changes/optimizer-index/evidence-before.json) 与 [evidence-after.json](../openspec/changes/optimizer-index/evidence-after.json)，运行器为 [evidence.py](../openspec/changes/optimizer-index/evidence.py)。SQLite VM 计数精度为 100 指令，收据的 0 表示少于 100，不能解释为零工作。Python 峰值仅来自 tracemalloc，不包含 SQLite 原生内存或整体 RSS。

| ID | 当前基线复现 | 产品修复 | 修复后改善与行为一致性 |
|---|---|---|---|
| DB-01 | 10,000 节点删除 10 文档：20 条 FTS 删除、3,437,500 VM 指令；IDA 保留在文档循环内读 FTS | touched IDs 临时表，同事务批量删两份 FTS 再级联；保留 IDA 一次 join 后按文档分组 | 2 条 FTS 删除、588,600 指令；剩余文档/节点/边/两份 FTS 摘要一致；三份 IDA 重建只读一次 FTS，节点/父边/xrefs/正文/meta 一致；缺失正文拒绝替换 |
| DB-02 | 10,000 节点末端精确路径：扫描 node-ID 索引、60,000 VM 指令 | `nodes_title(title,node_id)`，只在新 build 或显式 apply 的事务内创建 | `MULTI-INDEX OR` 使用 nodes_title 和 nodes_tree，少于 100 指令；命中与排名相同；旧 schema-v1 的只读查询/plan 不创建索引 |
| DB-03 | 10,000 行子树先取宽行再截断：12,585,357 字节 Python 峰值 | 精确 ID 计数 + 原排序的 LIMIT 500 宽行；整个 inspect 使用同一读取事务 | 仅取 500 宽行、903,883 字节峰值；count=9,999、返回 500、truncated=true 及完整 API 行为摘要相同；WAL 并发更新回归保持同一快照 |
| MEM-01 | 80 MiB 合成导出先完整读取：83,887,707 字节峰值才拒绝 | 上下文管理器读取 67,108,865 字节，即 64 MiB+1 | 请求读量有界、文件关闭、峰值 67,110,532 字节；保留相同超限错误；正常/恰好上限、哈希、模块路径和默认 plan 由新旧回归覆盖 |
| ALG-01 | 40,000 headings 的 sibling.index 推导 800,020,000 比较 | 一次枚举所有 children 准备 ordinal，按节点查表 | 无 sibling 搜索；包含既有正文分配共 80,000 child visits；完整物化行摘要与基线一致 |
| ALG-02 | 8,000 合成 provider 符号，规范化发生 31,996,000 同级标题比较 | `(parent_index,title)` 局部计数器 | 无扫描此前标题；规范化节点摘要一致，嵌套/同名/父级不同的 occurrence、tree_path、稳定 ID 保留；没有真实 parser 证据 |
| ALG-03 | 2,000 链接查目标 2,000 次、返回 4,002,000 行 | 每次事务缓存目标首行/首个标题/文件 fallback，跨新增、变更及 stale source 共享 | 1 查询、2,001 行；完整边摘要一致；多来源、空/未知/重复 anchor 和目标变化失效回归通过 |
| DATA-01 | 实际 update 的 8,001 文档/4,000 removed 合成输入：24,042,000 路径比较 | 保留有序 removed 列表，另建 membership set | 40,000 路径比较，计划文档摘要一致；此计数实验隔离 IO/FTS，独立真实 SQLite/文件回归验证批量删除+变更及 IDA 保留 |
| DATA-02 | 实际 SQL 800 命中，仪器化 str ID 记录 320,400 hash 调用 | 初始化一次 seen，包含直接 node-ID 首命中，逐行更新 | 1,600 hash 调用；全部命中/排名摘要一致，node-ID 优先、重叠去重后的原 rank gaps 和 top-k 保留 |
| SEC-02 | 32,000 未闭合 `[` 的生产提取器本次观察 0.388406 秒，空结果 | 单向 delimiter 扫描，不从每个 opening 重扫后缀 | str.find 覆盖 32,000 字符、本次观察约 0.0000354 秒，空结果一致；19,531 个长度≤6 的 delimiter 字符串和代表性边界样本与旧 regex 一致。时长仅旁证，无计时断言 |

七组行为 SHA-256（剩余数据库行、树 payload、完整物化行、syntax 节点、链接边、update 文档计划、精确命中）逐项相同。精确查询返回、IDA 错误及 Markdown 提取也分别比较；没有将各表相同推论为所有未测输入均相同。

## 实际运行与证据

以下均由本执行者运行，测试对象为最终生产代码。完整日志保存在本工作区忽略目录 `.verification/optimizer-index/`；正式收据已经随 OpenSpec 提交，远端不依赖本机日志才能理解结果。

| 结论 | 验证方式 | 结果与局限 |
|---|---|---|
| 改前既有索引/IDA 行为可作为基线 | `python -m pytest -q tests/test_index_unit.py tests/test_index_blackbox.py tests/test_ida_ingest.py` | exit 0，82 passed |
| 新测试能区分缺陷 | 将固定 commit 的七个已知 Python 模块和 index-contracts.json 导出到临时 import fixture，预载 baseline 包后运行 `tests/test_optimizer_index.py` | pytest exit 1（预期），23 failed、2 passed；没有新 worktree/分支。初次 harness 的迭代器/child-pass 记录错误已修正，最终基线回放以此数为准 |
| 最终索引行为回归 | `python -m pytest -q tests/test_optimizer_index.py tests/test_index_unit.py tests/test_index_blackbox.py tests/test_ida_ingest.py` | exit 0，107 passed；新文件 25 项 |
| 完整 Python 回归 | `python -m pytest -q` | exit 0，781 passed、5 skipped，203.55 秒；跳过不是通过 |
| 文档/命令/版本/路由契约 | `python -m reverse_skill --json gates all` | exit 0，output-v1 schemaVersion=1、ok=true、status=clean；doc-facts/version/routing-coherence 无 failures，版本仍 1.1.2 |
| 现有 Java gate | 在 burp-mcp-full 运行 `gradlew.bat check --no-daemon --offline` | exit 0，BUILD SUCCESSFUL；schedulerRegressionTest、test、check 实际执行；有既有编译/Gradle deprecated 提示，不是失败，没有启动 Burp |
| 逐 ID 原生产路径与修复路径 | `python -B openspec/changes/optimizer-index/evidence.py --baseline --output <before.json>`，同命令去掉 --baseline 运行 after | 均 exit 0，所有十 ID 产生收据；baseline 从 git show 的已知文件临时导入，未修改当前代码或审计目录 |
| 兼容语法 | 对五个生产文件、测试与 evidence runner 使用 `ast.parse(...,feature_version=(3,10))` | exit 0，Python 3.10 grammar passed；不能代替真实 3.10 runtime |
| 较旧 runtime 核心路径 | 现有 Python 3.11.16 运行临时合成 build/plan/inspect/search/import/update/rebuild smoke | exit 0；SQLite 3.53.1，同样采用两个 OR 索引；pytest 在该 interpreter 未安装，所以没有 3.11 完整 pytest 证据 |
| 文件/格式范围 | `git diff --check`；检查 changed paths 和 OpenSpec 相对引用 | exit 0；只提交 issue 允许路径；无额外依赖或公开字段 |

## 验收条件对应

| #57 验收条件 | 由什么验的 | 结果 |
|---|---|---|
| IDA 最多读取预算+1，超限早拒绝并保留正常/哈希/路径/授权行为 | `test_ida_loader_bounds_read_and_preserves_size_boundary`；原 tests/test_ida_ingest.py；MEM-01 收据 | 通过，导出为合成输入 |
| 畸形 Markdown 不平方扫描；ordinal/syntax/removed 单次准备 | delimiter 工作量/legacy equivalence、CountedChildren、parent-local syntax、many removed 回归及对应收据 | 通过；syntax 是 provider 输出规范化 |
| 一次链接构建复用目标/首标题，保留 anchor/ID/边/IDA | shared cache/stale update、IDA preservation 与既有 stable ID 回归；ALG-03 摘要 | 通过 |
| FTS 减少扫描；精确匹配计划与排序/去重/top_k | batch deletion/rollback、one preservation query、OR plan、exact priority/hash 回归 | 通过 |
| 确切 descendant_count、排序、最多 500 返回后代 | 1/500/501/502/2000 边界、10,000 行收据、WAL snapshot 回归 | 通过；数据库仍遍历全部 IDs |
| 只读 plan、坏索引保护、事务回滚、旧 schema、CLI 错误；索引只在 apply 创建 | legacy schema/rollback/import-plan 回归及既有 unit/blackbox/IDA 测试 | 通过 |
| syntax provider 输出一致性，真实 parser 缺失标明 | nested/duplicate provider 测试和 ALG-02 SHA-256；availability probe | 合成规范化通过；真实 parser 未验且未安装 |
| 每 ID 原复现/行为/改善，未运行失败缺口单列 | 上述十行、固定基线/当前收据、下面失败/未运行栏 | 已具备 |
| 相关回归、gates all、风险完整测试，保留公开契约 | 107 相关、781 完整通过 +5 跳过、gates all、Java check | 通过；环境边界见下 |
| 自己分支提交推送、一个自足 Draft PR、绑定当前 head | Draft PR 和 #57 的交付评论回读 | 远端交付收据记录实际链接/head；独立审查未完成 |

## 失败、跳过和未运行

- 改前的 23 个新测试失败属于复现预期；最初测试 harness 的 cursor iteration、child visits 统计与 duplicate suffix 预期曾导致无效失败，已经修正并重新对 baseline/current 回放。最终产品回归没有失败。
- 较旧 Python 测试启动：`py -3.11` 的本机 launcher 路径失效（exit 101）；使用现有 interpreter 后，完整 pytest 预检因缺 pytest 失败（exit 1）。随后仅用现有依赖完成真实 Python 3.11 核心 smoke，未安装任何东西。Python 3.10 没有本机 runtime；只验证其语法。
- 完整 suite 的 5 skipped：1 项 `tests/test_integrations.py:122` 因未安装 yara；4 项 `tests/test_journal_workflow.py:154` 因 Windows 不支持对应 literal quote/backslash 文件名。用 `python -m pytest -q -rs tests/test_integrations.py tests/test_journal_workflow.py` 回读得到 exit 0、27 passed、5 skipped；相关索引/IDA 107 项没有跳过，跳过不能计作已运行成功。
- 真实 tree-sitter provider 缺失；没有下载 parser/cache，也未运行真实 parser。真实 IDA/Burp 环境和目标调用未执行；合成 export、SQLite、provider 输出和 Java 测试不构成真实目标验证。
- 跨平台/不同 SQLite query planner 尚未完整验证；Windows Python 3.14.7/SQLite 3.50.4 完整测试及 Python 3.11.16/SQLite 3.53.1 核心 smoke 是本次证据范围。
- 用户级 skill 安装、真实主要工具操作、父级三 PR 集成、远端 CI 独立审查、合并、发布均由 #55 后续负责，未以本地绿灯替代。

## 副作用与剩余风险

没有公共契约、新依赖或跨源码所有权变化需要决定。新增 title index 是 apply 的数据库物理改变，可回滚且不变更 schema-v1；默认 plan 仍只读。临时 touched-ID 表只存在于该写连接，链接缓存只存在于一次操作；树查询新增只读事务会在查询期间保留数据库快照/读锁。

基线大型合成证据、测试日志和 Java 生成的工作区缓存/编译产物保存在 `.verification/optimizer-index/`，未入库；Java 输出从生产目录归档到该忽略目录，未改动其他组源文件。没有清理、切换、重置主工作区；没有启动服务、改全局配置、推 main、合并或发布。

剩余成本包括 FTS 单次 corpus 扫描、精确树 count/sort 遍历、IDA 保留分组的内存，以及已有子串检索回退。这些没有被称作常数工作量。独立审查和跨 PR 集成验收仍待父级执行；环境缺失的真实 parser/IDA/Burp 与 Python 3.10 runtime 验证仍待具备环境者补验。
