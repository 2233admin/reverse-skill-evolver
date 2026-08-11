# 🐉 Cybersecurity Skills Router — Kali Linux 2026.1 专供版

> **针对 Kali Linux 2026.1（内核 6.18）深度优化的 AI 安全技能路由系统**
>
> 让 Claude / Kiro / Cursor / Cline 等 AI 编辑器在 Kali 上自动识别安全任务 → 路由到正确方法论 → 调用本机工具链 → 自动沉淀经验

---

## 0. 给 AI 的第一条指令（读完 README 后立即执行）

> **先读取仓库根目录 `.aigx/protocol.aigx` 与 `RULES.md`，再通过确定性 router 进入任务。读取文档不会修改客户端全局配置。**

### 自动配置流程

```text
1. 检测仓库根目录并读取 `.aigx/protocol.aigx`
2. 读取 `RULES.md` 或 `kali/RULES-kali.md` 兼容启动桥
3. 调用 `python skills/scripts/route_task.py --task "<task>" ...`
4. 仅在 route 为 `ready` 后按需刷新工具索引或进入 child skill
```

> 详细流程见 `kali/RULES-kali.md`。AI 读完本 README 后应立即读取并执行 `kali/RULES-kali.md`。

### 报告格式示例

```markdown
✅ **Kali 逆向技能路由包已配置完成**

**安装路径**：/home/kali/cybersecurity-skills-router
**系统版本**：Kali 2026.1 (kernel 6.18)
**工具状态**：
- 预装可用：nmap, sqlmap, hashcat, hydra, metasploit, radare2, ...
- 需要安装：jadx, apktool（遇到时自动 bootstrap）
- MCP 已注册：mcp-kali-server, metasploitmcp, hexstrike-ai
- MCP 未注册（遇到时自动配置）：jshookmcp, anything-analyzer

**上下文 gate**：AIGX lint / boundary resolve 结果
**说明**：后续任务通过 `route_task.py` 确定性路由；缺失能力会显式 blocked，不会静默安装或回退。
```

---

## ⚡ 30 秒上手

```bash
# 克隆到 Kali
git clone <your-repo-url> ~/cybersecurity-skills-router
cd ~/cybersecurity-skills-router

# 一键初始化（安装新工具 + 配置 MCP + 刷新索引）
sudo bash kali/scripts/quick-setup.sh

# 完成后告诉你的 AI 客户端：
# "先读 .aigx/protocol.aigx 和 RULES.md，再用 route_task.py 路由当前任务"
```

之后遇到任何安全/逆向任务，AI 会自动路由。

---

## 🎯 为什么要用 Kali 版？

| 对比项 | 通用版（Windows） | Kali 专供版 |
|--------|:---:|:---:|
| 预装安全工具 | 0 个 | **50+ 个** |
| 安装 nmap/sqlmap/hashcat | 需要 winget/手动 | **已预装** |
| MCP 工具安装 | npm/Docker/手动配 | **apt install 一行** |
| 包管理 | winget + GitHub ZIP | **apt 统一** |
| 自动化实现 | Python 主链（`reverse-skill` CLI） | **Bash**（`kali/scripts/*.sh`） |
| 权限问题 | UAC/管理员 | **root 无障碍** |
| SecLists/字典 | 手动下载 | **apt install seclists** |

---

## 🔌 Kali 原生 MCP（核心优势）

Kali 2025.4/2026.1 官方仓库已收录三个 MCP 工具，**apt 直装即可让 AI 调用**：

```bash
# 一行命令配齐
sudo apt install mcp-kali-server metasploitmcp hexstrike-ai
```

| MCP 工具 | 功能 | AI 能做什么 |
|----------|------|-----------|
| **mcp-kali-server** | 终端桥接 | AI 直接执行 nmap/nxc/curl/gobuster 等任意命令 |
| **MetasploitMCP** | Metasploit 接口 | AI 搜索 exploit、生成 payload、管理 session |
| **HexStrike AI** | 150+ 工具编排 | AI 自动化多工具联动渗透测试 |

配合本包的路由系统，AI 不仅知道**用什么工具**，还能**直接调用**。

---

## 📦 Kali 2026.1 新增工具（已集成路由）

| 工具 | 用途 | 安装 |
|------|------|------|
| AdaptixC2 | C2 框架 / 对抗模拟 | `apt install adaptixc2` |
| Atomic-Operator | Atomic Red Team 测试 | `apt install atomic-operator` |
| SSTImap | SSTI 自动检测利用 | `apt install sstimap` |
| XSStrike | 高级 XSS 扫描 | `apt install xsstrike` |
| WPProbe | WordPress 枚举 | `apt install wpprobe` |
| Fluxion | WiFi 社工审计 | `apt install fluxion` |
| GEF | GDB 增强调试 | `apt install gef` |
| evil-winrm-py | WinRM 远程执行 | `apt install evil-winrm-py` |

所有工具都已注册到 `skills/routing.md` 路由矩阵，AI 遇到相关任务会自动调用。

---

## 🗂️ 目录结构

```text
cybersecurity-skills-router/
├── kali/                          # ← Kali 专属层
│   ├── README-kali.md             # 详细文档
│   ├── RULES-kali.md              # AI 路由规则（Kali 版）
│   ├── mcp-kali-example.json      # MCP 配置示例
│   └── scripts/
│       ├── quick-setup.sh         # 一键初始化
│       ├── bootstrap-reverse.sh   # 工具安装/补齐
│       ├── refresh-tool-index.sh  # 刷新工具索引
│       ├── ida-start.sh           # IDA MCP 启动
│       ├── bootstrap-manifest.json
│       └── lib/
│           └── tool-discovery.sh  # 工具发现库
├── skills/                        # 共享知识库
│   ├── SKILL.md                   # 总控入口
│   ├── routing.md                 # 路由矩阵（50+ 工具已注册）
│   ├── tool-index.md              # 工具状态索引
│   ├── apk-reverse/              # APK 逆向
│   ├── ida-reverse/              # IDA Pro
│   ├── js-reverse/              # JS/Web 逆向
│   ├── radare2/                 # radare2 CLI
│   ├── pentest-tools/           # 渗透测试（40+ 工具）
│   ├── reverse-engineering/     # 通用逆向方法论
│   ├── browser-automation/      # 浏览器自动化
│   ├── binary-diff/             # 符号迁移
│   ├── patch-diff-exploit/      # N-day 补丁差分→利用
│   ├── pwn-chain/               # RE→可用 exploit
│   ├── firmware-pentest/        # 固件渗透链
│   ├── edr-bypass-re/           # EDR 绕过逆向
│   ├── attack-chain/            # 多阶段攻击链
│   ├── docs-generator/          # 报告生成
│   ├── diagram-generator/       # 图表生成
│   └── field-journal/           # 通用先例与经 gate 晋级的模式
├── CTF-Sandbox-Orchestrator/      # 40+ CTF 子技能
├── RULES.md                       # Windows 版规则
├── README-kali.md                 # ← 你在看的文件
└── Readme.md                      # Windows 版说明
```

---

## 🚀 常用命令速查

```bash
# ─── 初始化 ───
sudo bash kali/scripts/quick-setup.sh          # 全新系统一键配置
bash kali/scripts/refresh-tool-index.sh        # 刷新工具索引

# ─── 安装工具 ───
bash kali/scripts/bootstrap-reverse.sh <tool>  # 安装单个工具
bash kali/scripts/bootstrap-reverse.sh mcp-kali-server metasploitmcp hexstrike-ai  # MCP 三件套
bash kali/scripts/bootstrap-reverse.sh adaptixc2 sstimap xsstrike wpprobe gef      # 2026.1 新工具
bash kali/scripts/bootstrap-reverse.sh coercer evil-winrm-py netexec responder     # AD 工具链

# ─── 启动 MCP 服务 ───
kali-server-mcp --port 5000                    # Kali 官方 MCP
metasploitmcp --transport stdio                # Metasploit MCP (stdio 模式)
metasploitmcp --transport http --port 8085     # Metasploit MCP (HTTP 模式)
bash kali/scripts/ida-start.sh                 # IDA Pro MCP

# ─── 验证 ───
cat skills/tool-index.md                       # 查看工具状态
nc -z 127.0.0.1 5000 && echo OK               # 检查 MCP 端口
```

---

## 🔄 工作流程

```
用户提出任务与当前 session 授权范围
    ↓
官方 AIGX lint + 编辑边界 resolve
    ↓
route_task.py 构建确定性 route
    ↓
输入 / capability / service / authorization gate
    ↓
ready → 进入 child skill；否则保持 blocked
    ↓
执行受控入口并验证 success oracle
    ↓
目标证据保存在仓库外；仅显式晋级通用脱敏模式
```

---

## 📋 支持的 AI 客户端

| 客户端 | 接入方式 | MCP 支持 |
|--------|---------|---------|
| Claude Code | 在项目中读取 `.aigx/protocol.aigx` → `RULES.md` | ✓ 完整 |
| Kiro | 项目级 `.kiro/steering/` 只作 AIGX 启动桥 | ✓ 完整 |
| Cursor | 在打开的项目中读取 `.aigx/protocol.aigx` → `RULES.md` | ✓ |
| Cline | 在打开的项目中读取 `.aigx/protocol.aigx` → `RULES.md` | ✓ |
| Windsurf | 在打开的项目中读取 `.aigx/protocol.aigx` → `RULES.md` | ✓ |
| Codex CLI / App | 项目级 instructions → AIGX → router | ✓ 完整 |

---

## 📖 详细文档

- **完整安装指南**：[kali/README-kali.md](kali/README-kali.md)
- **AI 路由规则**：[kali/RULES-kali.md](kali/RULES-kali.md)
- **MCP 配置示例**：[kali/mcp-kali-example.json](kali/mcp-kali-example.json)
- **路由矩阵**：[skills/routing.md](skills/routing.md)
- **架构图**：[ARCHITECTURE.md](ARCHITECTURE.md)

---

## ⚠️ 许可与免责

本包仅用于合法授权的安全研究、学习和 CTF 竞赛。

- 使用者需确保所有操作在法律允许范围内
- 未经授权对他人系统进行渗透测试属于违法行为
- 本包作者不对任何滥用行为承担责任
