# 审计剩项交接 — reverse-skill-evolver

接手这份文档的会话请先读本文件，再动代码。

## 仓库状态

| 项 | 值 |
|---|---|
| 仓库 | `F:/projects/reverse-skill-evolver` |
| 分支 | `main` |
| HEAD | `f4e2d38`（已推送到 `origin/main`，无 ahead/behind） |
| 测试 | `python -m pytest -q` → 840 passed, 5 skipped |
| 门禁 | `python scripts/run.py --json gates all` → `ok: true`，三项全 `clean` |
| 环境 | Windows / Python 3.14.7；`yara` 未安装（可选依赖） |

审计报告全文：`reports/code-optimization-audit-2026-10-19.md`。
架构报告：`reports/architecture-review-2026-10-19.md`。

## 已修完的 7 项（不要重做）

| # | 机制 | 修复 commit | 实测 |
|---|---|---|---|
| 1 | 未索引 FTS 逐节点查询 | `2285e91` | 783.8 ms → 20.3 ms（K=100） |
| 2 | 标题正则灾难性回溯 | `2285e91` | 3.1750 s → 0.00003 s |
| 7 | `index update` 重解析全部文件 | `5bbe0ec` | 31.5 → 11.2 ms（解析主导工件，2.7×） |
| 9 | `_depth_of` O(n·h) 祖先链遍历 | `5bbe0ec` | 9405 节点 0 处不一致 |
| 12 | JWT 正则无边界锚 | `5bbe0ec` | 1.4440 s → 0.00067 s |
| 13/14 | 扫描器无字节/条数上限 | `5bbe0ec` | 超限上报而非静默跳过 |

报告末尾 "Fixes applied" 段有每项的前后对比与等价性证明，可参照其验证手法。

`#7` 有个诚实的边界：在小文件工件上实测 **约 0%**（85.1 → 85.3 ms），因为
`scan_workspace` 的时间花在 `_path_islink`/`_path_isjunction`/`stat`/`open` 等系统调用上。
收益随文件内容大小增长，只在解析主导负载上成立——不要在报告里改写成普适加速。

## 待修：两个最高优先级

### #15 — MCP 响应无字节上限

文件：`reverse_skill/mcp.py:269-295`

现状：读取 MCP 服务端响应时按行/按事件累积，没有字节或事件数上限。`timeout` 只约束
**等待时长**，不约束内存——快速发送方可以在超时前把响应撑大。

风险机制：远端可返回无界流，客户端内存随对方输出线性增长，可被用作内存耗尽手段。

修复方向（需先实读该段确认）：给累积缓冲加显式上限（字节 + 事件数），超限时：
- 中止读取，返回明确错误（不是静默截断）
- 错误信息里带上「已读字节数 / 上限」，便于诊断
- 上限设为模块级常量，便于测试覆盖

验证要求：构造一个持续发送的服务端（本地 socket / mock），确认超限被触发且是本进程可控
的失败，不是 OOM。不能只测「正常响应仍能读取」。

### #23 — 同一制品按证据记录重复哈希

文件：`reverse_skill/case.py:389,447`

现状：每条证据记录都对制品做一次哈希。20 条记录 × 500 MiB 制品 → 约 9.8 GiB 读放大。

修复方向（需先实读两处调用链确认）：
- 按制品路径（+ 大小/mtime 或内容标识）缓存哈希，同一次操作内复用
- 缓存作用域限单次操作，不要引入跨进程持久缓存（会带来失效问题）
- 注意：若两处之间的文件可能被改写，缓存键要包含 mtime/size

验证要求：对同一制品构造多条证据记录，确认哈希只算一次（计数验证，不是计时）；
另测制品在两处调用之间被修改时不会返回陈旧哈希。

## 可复用的验证手法

这几条是本轮实测过的，值得沿用：

1. **等价性扫描**：改动正则/解析逻辑时，用旧实现与新实现跑同一批用例逐条比对输出，
   要求零不一致。本轮 #2 用了 16 个用例（含 `Title#` 不剥离、7 个 `#` 非标题等边界）。
2. **真实数据核不变量**：不只看单元测试。本轮 #9 是在全部 9405 个真实节点上核对
   「深度与旧遍历一致」和「父节点先于子节点」。
3. **A/B 用 `git stash` 拆分**：`git stash push -- <单文件>` → 跑 BEFORE → `git stash pop`
   → 跑 AFTER。**必须拆成独立命令**，不要打包成一条（看不到副作用，且用户明确要求拆开）。
4. **lazy API 必须消费后计时**：`finditer`/生成器返回后不消费则不计时。本轮曾因此误判
   JWT 正则「不可复现」，被 lane 纠回。计时函数里要显式 `list(...)` 或遍历。
5. **条件化的结论**：性能修复要写清生效条件。本轮 #1 保留 K<5 的逐节点循环（K=1 实测
   循环更快），#7 写明「仅解析主导工件」，都是这个原则。

## 已核实为误报 / 已优化的项（不要重复排查）

报告 "Findings considered and cleared" 段列出了这些，摘要：

- `journal_mode=OFF` / `synchronous=OFF` / `temp_store=MEMORY` + 单 `BEGIN IMMEDIATE` —— 已优化
- `insert_fts_rows_bulk` —— 已批量化
- reader 连接生命周期 —— `finally: close()` 完整
- `swarm` 解析 —— 单次，无需改
- MCP 客户端复用 —— 正确
- YARA RPC —— 已批处理
- FTS5 trigram 构建 1.27 s、`executemany` 1.50 s —— **属必须做的工作，明确不优化**

## 工具纪律（本轮踩过的坑）

- **shell 用 `exec_command`**；文件读用 `read`；目录列举用 `read <dir>`/`glob`；搜索用 `grep`；
  编辑用 `edit`。**禁止**用 `eval(language="py")` 包装 `git`/`os.walk`/`subprocess.run` 充当 shell。
- **`exec_command` 命令要短**：用户明确要求拆分（曾拒一条 871 字符、含三个程序且会写入的调用）。
- `find` 工具（judge）多次因 `typesafe/jev-latest` API 403 失败，不可依赖，改用 `grep`。
- PowerShell 经 `exec_command` 需 `shell: "powershell"`；`$_` 会被 bash 转义破坏。

## 未做的事

- **未发版**：`v1.2.0-beta.2` tag 仍指向 `1b62a45`，不含本轮的 6 个 commit。push 只更新了 `main`。
- 审计 #3–6、#8、#10、#11、#16–22、#24–30 未修，均在报告发现清单里，含 `file:line` 与分级。

## 工作树卫生

本轮结束时的未跟踪文件（**不属于本轮工作，未提交**）：
`ARTEX-PATTERN-COMPARISON.md`、`ARTEX-PORT-PLAN.md`、
`reports/pr62-code-review-2026-10-17.md`、`skills/chains/`。

探测脚本（`probe_jwt.py`、`probe_scan.py`、`bench_update.py`）已清理；如需 A/B 基准要重写。
