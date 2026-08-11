# 示例：对本仓自身跑一夜（dogfood）

一份**已填好的** OVERNIGHT.md 应用实例：目标是对 reverse-skill-evolver 自身做一次无人值守过夜运行——收敛 evolution 控制面的规范形 + 路由一致性。把这份填充应用到 `OVERNIGHT.md` 的副本上即可投给 agent。

> 本示例的 `TEST_CMD` 使用 `python -m reverse_skill gates routing-coherence`（本仓路由一致性校验的 Python 门禁，作为过夜运行的回归门）。`LINT_CMD` 为 Python 语法编译检查（项目自动化全 Python，无 PowerShell 门禁）。

## 已填 slot

| Slot | 填充值 | 为什么这么填 |
|---|---|---|
| `{{DEADLINE}}` | `2026-08-08T08:00:00+08:00` | 次日早上 8 点停机 |
| `{{TEST_CMD}}` | `python -m reverse_skill gates routing-coherence` | 全仓路由一致性（Python 门禁）：routing.json 合法 + 所有被引用 skill 路径存在 |
| `{{LINT_CMD}}` | `python -m compileall -q reverse_skill skills/scripts scripts` | Python 语法编译检查（项目自动化全 Python） |
| `{{LOC_CMD}}` | `python -c "import pathlib; print(sum(1 for p in pathlib.Path('skills').rglob('*') if p.is_file() and p.suffix in {'.py','.md','.json'} and any(not l.strip().startswith(('#','//','<!--')) and l.strip() for l in p.read_text(encoding='utf-8',errors='ignore').splitlines())))"` | 非注释非空行数（Python） |
| `{{BENCH_CMD}}` / `{{PERF_METRICS}}` / `{{PERF_TOLERANCE}}` | 无（本仓无性能面） | 删除基准节与对应 slot |
| `{{ISSUE_LIST}}` | ① routing.json 缺 overnight-run 路由 ② evolution schemas 无配套校验器 ③ field-journal 分层目录空、无 validated 先例 | Phase 1 目标（triage 后按把握度修） |
| `{{TARGET_MODULE}}` | `skills/evolution` + `skills/routing.json` + `skills/routing.md` | 控制面 + 路由双表 |
| `{{SPEC_FILE}}` | `skills/evolution/SKILL.md` + `skills/routing.json` | 形状唯一事实来源 |
| `{{ALLOWED_COMPONENTS}}` | markdown / yaml / json / powershell（PS 5.1 兼容）；现有 templates 与 schemas；`skills/scripts/*.ps1` | 成分白名单 |
| `{{BANNED_PATTERNS}}` | `reset --hard`、`force-push`、`rebase`、未过 promotion gate 改 stable 路由、删除或降级 validated 证据、`.night/` 外净新增文件 | 语法红线 |
| `{{QUARANTINE_BUDGET}}` | `0` | 上限不是配额，0 才是预期值 |
| `{{MAX_PASSES}}` | `3` | 连续 3 轮未收敛 → 超预算结局 |
| `{{PHASE2_BUDGET}}` | `4h` | Phase 2 时间上限 |
| `{{ESCAPE_HATCHES}}` | 无 | 本仓无逃生舱语法 |
| `{{SCOPE_PREFIX}}` | `overnight` | commit 前缀 |

## 运行前检查（三条命令）

```powershell
# 1. 模板冒烟：slot 质量不过关就不出发
powershell -NoProfile -ExecutionPolicy Bypass -File skills/overnight-run/scripts/validate-slots.ps1 -TemplatePath <已填模板副本>

# 2. 脚手架：.night/ 五文件 + night 分支 + pre-commit hook
powershell -NoProfile -ExecutionPolicy Bypass -File skills/overnight-run/scripts/new-overnight.ps1 -LintCmd "<上面 LINT_CMD>" -BannedPatterns @('reset --hard','force-push','rebase') -TargetModule "skills"

# 3. 投递：把已填模板整份作为唯一指令给 agent，独立运行至 DEADLINE
```

## 早上的 review 顺序

1. `.night/REPORT.md`：三句话复述 + 各 Phase 结局（达成 / 收敛待复核 / 超预算 / 规格阻塞 / 诊断模式）
2. `git log --oneline -- .night/BASELINE.md`：应只有一行（基线封存证明）
3. Phase 2 映射表（规格步骤 ↔ 代码构造，一一对应）；`QUARANTINE.md` 摘要（本示例预期为 0 条）
4. 每个 commit 独立、格式合规（§5）
5. 目标运行证据保持外置；通过 oracle 且能由合成 fixture 复现的通用抽象 → promotion review，未通过不得写入 field-journal
