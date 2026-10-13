# 通用 Scope 契约（任务启动硬门槛）

> **MUST**：任何安全/逆向/渗透任务在 **ACT 之前** 在用户项目或 `work/<case>/` 落地 `scope.md`。
> 无 scope → 只允许读文档/路由，**禁止** 对目标主动扫描、Hook、利用。
> 字段名保持英文键；机器可读枚举与别名由 `reverse_skill/data/case-contracts.json` 冻结（本文件是人工镜像，禁止制造平行枚举）。

## 如何初始化

```bash
reverse-skill case init --hint "<任务一句话>" --case-name "my-case"
# 默认产出：当前目录的 work/<case>/scope.md 等
# 从其他目录调用时显式指定：--package-root "C:\path\to\analysis-project"
```

Presets（减少合法本地/CTF 工作的误拒摩擦）：

| preset | auth.status | auth.basis | network_profile.mode | 别名 |
|---|---|---|---|---|
| `offline-sample` | granted | own_system | offline | own-sample, local-sample |
| `ctf-public` | granted | ctf_public | authorized_target_only | ctf |
| `own-system` | granted | own_system | lab_only | lab-only |

## scope.md 完整模板

```markdown
# Case Scope

## meta
- case_id: {YYYYMMDD-short}
- created: {ISO-8601}
- operator: {name or local}
- primary_skill: {from reverse-skill route}
- primary_id: {route id from reverse-skill route, or no_route}
- lead_role: lead
- specialist_roles: []

## auth
- status: granted | pending | denied | unknown
- basis: written_contract | bug_bounty_scope | ctf_public | own_system | lab_only
- evidence_of_auth: {ticket/path or "CTF public" or "owner-operated"}
- MUST NOT proceed if status != granted

## in_scope
- assets: []          # hosts, domains, APK paths, binaries, URLs
- surfaces: []        # web, mobile, binary, network, api
- activities: []      # recon, reverse, exploit_validate, report

## out_of_scope
- assets: []
- activities: []      # e.g. DoS, phishing real users, data exfil

## network_profile
- mode: offline | lab_only | authorized_target_only | unrestricted_lab
- notes: |
    offline = 无对外发包（纯静态/本地样本）
    lab_only = 仅 lab/VM IP
    authorized_target_only = 仅 in_scope 资产
- MUST NOT use unrestricted against production without written auth

## deliverables
- report: true
- field_journal: true
- diagrams: true
- timeline: true

## constraints
- timebox: {}
- stealth: low | medium | high
- data_handling: anonymize | no_user_pii

## signoff
- ready_for_act: false
- checklist:
  - [ ] auth.status = granted
  - [ ] in_scope.assets non-empty OR offline sample path set
  - [ ] network_profile.mode chosen
  - [ ] out_of_scope reviewed
```

## network_profile 归一化

规范值：`offline | lab_only | authorized_target_only | unrestricted_lab`。

`reverse-skill case init` 接受别名并归一化（`case-contracts.json` 冻结）：

| 输入 | 归一化 |
|---|---|
| `lab` | `lab_only` |
| `authorized`, `auth` | `authorized_target_only` |
| `offline_only` | `offline` |

未知 mode 在 init 时直接失败（exit 2），不会生成 ready 的非法 scope。review 只接受规范值。

## 路由挂钩（AI 必须执行）

```text
RULES / .aigx / SKILL:
  1) reverse-skill route → PRIMARY
  2) reverse-skill case init 或手写 scope.md
  3) auth 未 granted → STOP，只允许补授权材料
  4) ready_for_act = true → 打开 PRIMARY SKILL.md → ACT
```

## network_profile 速查

| mode | 允许 | 禁止 |
|------|------|------|
| `offline` | 静态分析、本地文件、模拟 | 任意外连、公网 RPC |
| `lab_only` | lab/CTF 靶机网段 | 生产/未授权 IP |
| `authorized_target_only` | in_scope 列表 | 列表外资产 |
| `unrestricted_lab` | 隔离实验网（书面） | 互联网生产 |

## 特色

- 纯 Markdown，**无数据库**
- 与 tool-index / bootstrap 正交：scope 管「能不能打」，tool-index 管「用什么打」
- 机器可读契约单一来源：`reverse_skill/data/case-contracts.json`
