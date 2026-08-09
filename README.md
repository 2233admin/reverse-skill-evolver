> **[Chinese Version / 中文版](README_zh.md)**

> **AIGX is mandatory.** `.aigx/` is the canonical project-context plane; `RULES.md` and agent-specific files are thin bootstraps into it. Project-aware routing fails closed when the target project has no valid AIGX genome or an explicit edit target lacks a boundary entry.

<p align="center">
  <img src="assets/reverse-skill-evolver-cover.png" alt="Reverse Skill Evolver tactical cover" width="100%" />
</p>

# Cybersecurity Skills Router / Reverse-Engineering Skill Routing Pack

> This package can be placed in any directory. In the following text, `<REPO_ROOT>` is the directory containing this README, and `<SKILL_ROOT>` is `<REPO_ROOT>\skills`.

---

## 0. First Instruction for the AI

> **Use the repository's AIGX genome before routing or editing. Do not write global client configuration as a side effect of reading this package.**

### Startup Process

```text
1. Detect `<REPO_ROOT>` from this README and set `<SKILL_ROOT>` to `<REPO_ROOT>\skills`.
2. Read `.aigx\protocol.aigx`, the relevant concern genomes, and `RULES.md`, which is only a compatibility bootstrap.
3. For project-aware work, validate the target project's AIGX genome and each known edit boundary.
4. Run `python "<SKILL_ROOT>\scripts\route_task.py" ...`; continue only when the returned plan is `ready`.
```

`RULES.md` points clients into the canonical AIGX context and deterministic router. It does not inject global rules, install tools, or replace the route preflight.

### Example Report Format

```markdown
✅ **Reverse-Engineering Route Preflight Complete**

**Repository root**: <REPO_ROOT>
**Route status**: ready | blocked | no_route | invalid
**Selected workflow**: <skill path>
**Required input/capabilities**: <requirements>
**Next action**: <controlled dispatch or blocker resolution>
```

---

This is not a “single-tool installer." It is a **reverse-engineering skill routing pack** for code AI clients such as Claude Code, Codex CLI, Cursor, Cline, Windsurf, and other clients that support rules, prompt injection, MCP, or external tool calls.

It solves two problems:

1. When the AI encounters APK / binary / frontend JS / packet-capture / CTF tasks, it follows the correct methodology and sub-skill first instead of guessing randomly.
2. It consolidates local tools, MCP servers, script entry points, and workflows into a reusable directory structure that is easy to migrate to a new machine.

---

## 1. What Is Included in This Package

At present, it is recommended to understand the whole package as two layers:

```text
<REPO_ROOT>\
├── Readme.md                     # The installation/distribution guide you are reading now
├── CTF-Sandbox-Orchestrator\     # Full CTF competition stack (40+ sub-skills)
└── skills\                       # Main skills directory
    ├── SKILL.md                  # Main controller entry point
    ├── evolution\                # GOAL contracts, capability graph, TraceCards, promotion gates
    ├── overnight-run\            # Unattended overnight run contract (OVERNIGHT.md v2) + scaffolding
    ├── routing.md                # Scenario → skill dispatching (routing matrix)
    ├── routing.json              # Machine-readable routing mirror
    ├── CONTRIBUTING.md           # Guide for adding new skills
    ├── tool-index.md             # Tool index (auto-generated)
    ├── capability-graph.json     # Session-level tool/MCP/service health graph (auto-generated)
    ├── scripts\                 # Tool-index refresh and shared scripts
    ├── field-journal\           # Generic precedents and promoted patterns
    ├── api-security\            # API security testing (REST/GraphQL/WebSocket/SOAP)
    ├── apk-reverse\             # APK reverse engineering
    ├── attack-chain\            # Multi-stage attack-chain orchestration
    ├── binary-diff\             # Cross-version symbol migration
    ├── browser-automation\      # Browser + desktop automation (Playwright + OpenReverse)
    ├── diagram-generator\       # Diagram generation (Mermaid / Graphviz / PlantUML)
    ├── docs-generator\          # Technical document/report generation
    ├── edr-bypass-re\           # EDR bypass reverse engineering (red-team delivery)
    ├── firmware-pentest\        # Firmware penetration-testing chain (OWASP FSTM)
    ├── ghidra-reverse\          # Ghidra reverse engineering (GhydraMCP, free IDA alternative, not yet battle-tested here)
    ├── ida-reverse\             # IDA Pro reverse engineering
    ├── js-reverse\              # Frontend JS / browser-chain reverse engineering
    ├── llm-security\            # LLM/AI security testing (OWASP LLM Top 10 + Agentic AI Top 10)
    ├── malware-analysis\        # Malware analysis (YARA/Sigma/sandbox/IOC extraction)
    ├── mobile-reverse\          # Mobile reverse engineering (Android + iOS, Frida/Objection/MSTG)
    ├── patch-diff-exploit\      # N-day patch diff → exploitation
    ├── pentest-tools\           # Penetration-testing toolchain
    ├── pwn-chain\               # RE → usable exploit (stack / heap / kernel)
    ├── radare2\                 # radare2 CLI reverse engineering
    ├── reverse-engineering\     # General reverse-engineering methodology
    └── supply-chain-security\   # Software supply-chain security (SBOM/SCA/CI-CD)
```

If you also use the CTF knowledge base, it is recommended to place it under the root of this package (the current default structure):

```text
<REPO_ROOT>\
├── skills\                       # Main skills directory
├── CTF-Sandbox-Orchestrator\     # CTF competition sub-skills (40+)
└── Readme.md
```

This allows the relative paths in `routing.md`, such as `../CTF-Sandbox-Orchestrator/...`, to resolve correctly from `skills/`.

> If you place `CTF-Sandbox-Orchestrator` outside this package, such as `F:\CTF-Sandbox-Orchestrator\`, you need to manually adjust the relative paths in `routing.md`.

---

## 2. Recommended Installation Approach

### 2.1 Recommended Directory Layout

After downloading, users are recommended to place the package as follows:

```text
<REPO_ROOT>\             # Package root; drive letter can be changed
<REPO_ROOT>\skills\      # <SKILL_ROOT>
C:\Users\<your username>\Tools\jadx\
C:\Users\<your username>\Tools\apktool\
C:\Users\<your username>\AppData\Local\Android\Sdk\platform-tools\
C:\Users\<your username>\AppData\Local\Programs\Python\Python3xx\
C:\Program Files\nodejs\
D:\APP\IDA\                            # Example only; customize as needed
C:\Tools\radare2\                      # Optional
```

### 2.2 Do Not Treat These Values as Hard Requirements

Many scripts, documents, and tool indexes in this package contain **sample paths**. These paths only represent one machine’s layout. They do not mean that you must copy them exactly.

After migrating to a new machine, especially check paths such as:

- `D:\APP\IDA`
- `<user directory>\...`
- `<REPO_ROOT>\...`

If you change drive letters, usernames, or tool installation directories, adjust them according to the “Required Changes After Migration" section in this document.

---

## 3. Quick Start

### 3.1 If You Only Want to Put the Skill Pack in Place First

1. Put the whole directory somewhere you like, for example: `<REPO_ROOT>\`
2. Go to `skills\SKILL.md`
3. When handling a task, read files in this order:
   1. `SKILL.md`
   2. `evolution\SKILL.md`
   3. `routing.json` + `routing.md`
   4. The `SKILL.md` in the corresponding subdirectory
   5. Read `capability-graph.json` / `tool-index.md` only when you need to confirm local tools

### 3.2 If You Want Any Code CLI to Automatically Use This Routing

You need at least:

- A code CLI that supports custom rules / system prompts / project instructions / hooks
- A way to inject “read the routing file first for reverse-engineering tasks" into the model context
- If direct external capabilities are needed, configure MCP or an equivalent tool bridge
- This package’s `SKILL.md`, `evolution\SKILL.md`, `routing.json`, `routing.md`, `capability-graph.json`, and `tool-index.md`

If you already have Claude hooks, Codex CLI project instructions, Cursor Rules, Cline custom instructions, or Windsurf Rules, update any old paths inside them to the current installation path.

---

## 4. Dependency Table: What to Install, Where to Download, and Where to Put It

The following tables are grouped by “required / commonly used / optional enhancement."

### 4.1 Core Clients and Runtimes

| Component | Required? | Project URL | Purpose | Recommended Location | Installation / Startup |
|---|---|---|---|---|---|
| Claude Code | Recommended | https://github.com/anthropics/claude-code | Main AI client, best suited for this package | User’s own Claude environment | Follow official instructions; then connect this package path and MCP/hooks |
| Node.js 22.12+ | Required for JS/MCP | https://nodejs.org/ | Runs `npx`, `jshookmcp`, and local JS reproduction | `C:\Program Files\nodejs\` | Confirm with `node -v` and `npx -v` |
| Python 3.x | Commonly used | https://www.python.org/ | Runs Frida, helper scripts, and common `ida-mcp` distributions | `C:\Users\<user>\AppData\Local\Programs\Python\Python3xx\` | Confirm with `python --version` and `pip --version` |
| Java / JDK | Required for APK | https://adoptium.net/ or https://www.oracle.com/java/ | Runs Java tools such as `jadx` and `apktool` | Default system JDK path is fine | Confirm with `java -version` |

### 4.2 APK / Android Reverse-Engineering Tools

| Component | Required? | Project URL | Purpose | Recommended Location | Installation |
|---|---|---|---|---|---|
| jadx | Common for APK | https://github.com/skylot/jadx | Java decompilation | `C:\Users\<user>\Tools\jadx\` | Download release zip and extract; ensure `bin\jadx.bat` exists |
| apktool | Common for APK | https://apktool.org/ | APK unpacking / rebuilding | `C:\Users\<user>\Tools\apktool\` | Download Windows package; place `apktool.bat` and `apktool.jar` in the same directory |
| Android platform-tools | Common for dynamic debugging | https://developer.android.com/tools/releases/platform-tools | Provides `adb` | `C:\Users\<user>\AppData\Local\Android\Sdk\platform-tools\` | Download and extract; confirm `adb.exe` works |
| Android Build-Tools | Common for resigning | https://developer.android.com/tools/releases/build-tools | Provides `apksigner` and `zipalign` | Android SDK `build-tools\<version>\` | Install through Android SDK Manager; without it, the full resigning chain cannot run |

### 4.3 Dynamic Analysis and Browser-Side Tools

| Component | Required? | Project URL | Purpose | Recommended Location | Installation |
|---|---|---|---|---|---|
| Frida / frida-tools | Common for dynamic hooking | https://frida.re/ | Java / native dynamic injection | Python Scripts directory | Usually `pip install frida-tools`; confirm `frida` and `frida-ps` work |
| anything-analyzer | Web/traffic enhancement | https://github.com/Mouseww/anything-analyzer | Browser automation, HTTP capture, AI analysis | Any code directory, e.g. `C:\work\anything-analyzer-main\` | Current package metadata indicates `pnpm`; common flow: `pnpm install` → `pnpm dev` |
| jshookmcp | JS reverse-engineering enhancement | https://github.com/vmoranv/jshookmcp | Browser/CDP/Hook/Network/SourceMap/AST execution surface | No fixed directory; start with `npx` | Not a standalone bare tool; register and enable it in the MCP client first |

### 4.4 Binary Reverse-Engineering Tools

| Component | Required? | Project URL | Purpose | Recommended Location | Installation |
|---|---|---|---|---|---|
| IDA Pro | Common for deep binary RE | https://hex-rays.com/ida-pro/ | Decompilation, xrefs, data flow, renaming, type recovery | Example: `D:\APP\IDA\` | Install IDA and point `IDADIR` to its root directory |
| idalib-mcp | Required for `ida-reverse` | https://github.com/mrexodia/ida-pro-mcp | Exposes `idapro_*` MCP tools or a local HTTP service | Commonly installed in Python Scripts | `pip install git+https://github.com/mrexodia/ida-pro-mcp.git`, then `ida-pro-mcp --install` |
| radare2 | Optional | https://github.com/radareorg/radare2 | CLI reconnaissance, disassembly, diffing, patching | `C:\Tools\radare2\` | Confirm `r2`, `rabin2`, `rasm2`, `radiff2`, etc. work |

### 4.5 Supporting Knowledge Base

| Component | Required? | Project URL | Purpose | Recommended Location |
|---|---|---|---|---|
| CTF-Sandbox-Orchestrator | Strongly recommended for CTF | Use your local repo/private distribution URL | CTF controller and 40+ `competition-*` sub-skills | Recommended to place beside this package, e.g. `F:\CTF-Sandbox-Orchestrator\` |

---

## 5. Supported Scenarios by Default

### 5.1 Main Modules Under `skills\`

| Module | Directory | Main Purpose |
|---|---|---|
| Main controller entry | `SKILL.md` | Read the global map first, then decide which sub-skill to enter |
| Self-evolution control plane | `evolution\` | GOAL contracts, capability graph, step-level TraceCards, and promotion gates |
| Unattended overnight run | `overnight-run\` | Fill slots → validate → scaffold (.night/ + night branch + pre-commit) → run to DEADLINE → morning review |
| Routing table | `routing.md` | Dispatch by target type, user intent, and toolchain |
| Machine routing mirror | `routing.json` | Structured routes, fallback edges, required capabilities, and success oracles |
| Tool index | `tool-index.md` | Check whether local tools exist, where they are, and which scripts call them |
| Capability graph | `capability-graph.json` | Session-level tool path, version, MCP registration, service health, and smoke status |
| APK reverse engineering | `apk-reverse\` | Unpack, jadx, smali, repackaging, Frida, native dispatch |
| IDA Pro | `ida-reverse\` | Deep binary RE and `idapro_*` workflows |
| JS / Web | `js-reverse\` | Frontend signatures, request chains, environment simulation, SourceMap / AST / Hook |
| radare2 | `radare2\` | CLI reconnaissance, strings, imports/exports, patching |
| General methodology | `reverse-engineering\` | Cross-language, cross-platform, anti-analysis, pattern library |
| Browser and desktop automation | `browser-automation\` | Playwright browser operations + OpenReverse desktop app automation |
| Cross-version symbol migration | `binary-diff\` | Migrate symbols from old versions to new versions, infer without PDB, LLM-assisted bulk migration |
| N-day patch diff → exploit | `patch-diff-exploit\` | Locate vulnerable points from vendor patches, write PoC, weaponize N-day |
| RE → exploit chain | `pwn-chain\` | From reverse engineering to usable exploit: stack/heap/kernel pwn, pwntools, libc-database |
| Firmware penetration chain | `firmware-pentest\` | OWASP FSTM full chain: extraction → EMBA → Firmadyne emulation → AFL++ fuzzing → real-device validation |
| EDR bypass RE | `edr-bypass-re\` | Reverse EDR hook tables / ETW / AMSI → direct syscall / Hell’s Gate / call-stack spoofing |
| Penetration-testing toolchain | `pentest-tools\` | Nmap / Nuclei / SQLMap / FFUF / Hashcat and 20+ tool MCP workflows |
| Diagram generation | `diagram-generator\` | Mermaid / Graphviz / PlantUML diagrams for attack paths, architecture, data flow |
| Technical documents | `docs-generator\` | Automatically generate RE / pentest / CTF reports after a task |
| LLM/AI security | `llm-security\` | OWASP LLM + ASI Top 10: prompt injection, agent security, **agent obedience engineering** |
| Operational precedent library | `field-journal\precedent-*.md` | Generic, anonymized methodology; never proof of authorization for a specific target |

### 5.2 Recommended Entry Points

Use the following routing first:

- APK / Android → `apk-reverse\SKILL.md`
- exe / dll / so / elf → `ida-reverse\SKILL.md` or `radare2\SKILL.md`
- Frontend signature / encrypted parameters → `js-reverse\SKILL.md`
- HTTP capture / browser sampling / request replay → anything-analyzer + `js-reverse`
- Penetration testing / port scanning / vulnerability scanning → `pentest-tools\SKILL.md`
- Firmware / IoT / router pentesting → `firmware-pentest\SKILL.md`
- N-day / patch diff / CVE PoC writing → `patch-diff-exploit\SKILL.md`
- Exploit writing / pwn / stack-heap-kernel exploitation → `pwn-chain\SKILL.md`
- EDR / AV bypass / red-team delivery → `edr-bypass-re\SKILL.md`
- Browser/desktop automation → `browser-automation\SKILL.md`
- Symbol migration / cross-version comparison → `binary-diff\SKILL.md`
- Diagrams / architecture diagrams / attack-path diagrams → `diagram-generator\SKILL.md`
- CTF challenge → dispatch first through the `CTF-Sandbox-Orchestrator` controller

---

## 6. Startup and Verification

## 6.1 Refresh the Tool Index

Do not trust someone else’s scan result for long. After migrating to a new machine, refresh it first:

```powershell
powershell -File "<SKILL_ROOT>\scripts\refresh-tool-index.ps1"
```

After success, check:

- `skills\tool-index.md`
- `skills\tool-index.json`
- `skills\capability-graph.json`

> Important: `yes/no` in `tool-index.md` only represents the scan result on the current machine. It does not guarantee the same status on your machine.
> Use `capability-graph.json` for current session facts such as MCP registration, service ports, smoke status, and promotion-gate policy.

### Automatic Task Routing

Route every task through the deterministic planner before opening a child skill:

```powershell
python "<SKILL_ROOT>\scripts\route_task.py" `
  --task "Analyze this EXE with static decompilation first" `
  --input-path "C:\path\to\sample.exe" `
  --pretty
```

For source or application projects, also pass `--project-path "<project root>"` and each known edit as `--aigx-target "<repo-relative path>"`. The target project's AIGX genome and edit boundaries are mandatory. Code Intel/Sentrux evidence is authoritative only for that same project.

- `status=ready`: run the controlled `dispatch.command` or enter the selected skill's first action.
- `status=blocked`: resolve the reported input, capability, service, authorization, or project-context blocker.
- `status=no_route`: add or propose a route instead of force-fitting a nearby skill.
- `status=invalid`: correct the task contract.

Only `--execute` runs a returned controlled entrypoint. Without it, the router is read-only and emits a machine-readable plan.

## 6.2 IDA Pro Chain

### Start the IDA MCP HTTP Service

Current script entry point in this package:

```powershell
powershell -File "<SKILL_ROOT>\ida-reverse\scripts\start.ps1"
```

The current script reuses a healthy service by default. With explicit `-ForceRestart`, it terminates only the process tree verified on the requested port, starts the service in the background, waits for readiness, and outputs `OK:<tool count>` or `ERR:timeout`.

### Open a Sample

```powershell
powershell -File "<SKILL_ROOT>\ida-reverse\scripts\open.ps1" -Path "C:\path\to\sample.exe" -TimeoutSeconds 600
```

Features:

- Detects the current `idb_open` / legacy `idalib_open` API and bypasses client-side schema issues
- Automatically copies System32 files to a temporary directory
- Falls back to a temporary copy when old database files are locked
- Long analysis prints `INFO:opening:...`

### Values You Must Change

Default scripts still contain machine-specific values, such as:

- `ida-reverse\scripts\start.ps1`
  - `IDADIR`
  - `ServerPath`
- `ida-reverse\scripts\open.ps1`
  - `IDADIR`
  - `TempDir`

After migration, change these to real values for your machine.

## 6.3 anything-analyzer

Current local project metadata shows:

- Project name: `anything-analyzer`
- Package manager: `pnpm@10.24.0`
- Common scripts: `dev` / `build` / `preview`

Common development startup:

```powershell
pnpm install
pnpm dev
```

This package only assumes that it eventually exposes an MCP endpoint such as:

```text
http://localhost:23816/mcp
```

If the address, port, or auth headers differ, update your MCP client configuration accordingly.

## 6.4 jshookmcp

`jshookmcp` is not positioned as a standalone main entry point in this package. It is an enhanced execution surface for `js-reverse`.

It is suitable for:

- Browser automation
- CDP debugging
- JS hooking
- Network interception
- SourceMap / AST-assisted understanding

### Example Registration

```json
{
  "mcpServers": {
    "jshook": {
      "command": "npx",
      "args": ["-y", "@jshookmcp/jshook@latest"],
      "env": {
        "JSHOOK_BASE_PROFILE": "search"
      }
    }
  }
}
```

Notes:

- `jshookmcp = yes` in `tool-index.md` only means the machine has `node/npx` conditions
- It does not mean that Claude / Cursor / Cline has registered and enabled it
- If it is not enabled in the MCP client, the AI cannot call it

## 6.5 APK Script Chain

Common scripts:

- `apk-reverse\scripts\decode.ps1`
- `apk-reverse\scripts\frida-run.ps1`
- `apk-reverse\scripts\rebuild-sign-install.ps1`
- `apk-reverse\scripts\manifest-summary.ps1`

After migration, verify first:

```powershell
jadx --version
apktool --version
adb version
frida-ps -U
```

If `apksigner` / `zipalign` still show as `no` in `tool-index.md`, Android Build-Tools have not been installed yet.

---

## 7. How to Integrate with Claude Code / Codex CLI / Other AI Clients

## 7.1 General Integration Principles

Whether you use Claude Code, Codex CLI, Cursor, Cline, Windsurf, or another code AI client, what you actually need to integrate are these four things:

1. This package directory
2. MCP or equivalent external tool endpoints
3. A stable prompt-injection method
4. The principle of “route first, execute second"

### MCP Example

```json
{
  "mcpServers": {
    "anything-analyzer": {
      "url": "http://localhost:23816/mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_TOKEN>"
      }
    },
    "idapro": {
      "url": "http://127.0.0.1:13337/mcp"
    },
    "jshook": {
      "command": "npx",
      "args": ["-y", "@jshookmcp/jshook@latest"],
      "env": {
        "JSHOOK_BASE_PROFILE": "search"
      }
    },
    "burpsuite": {
      "command": "node",
      "args": ["<REPO_ROOT>/burp-mcp-full/mcp-bridge.js"]
    }
  }
}
```

### Minimum Prompt Requirements

Every client must expose the same three-step entry chain:

1. `<REPO_ROOT>\.aigx\protocol.aigx` — canonical context and edit-boundary contract.
2. `<REPO_ROOT>\RULES.md` — thin compatibility bootstrap.
3. `<SKILL_ROOT>\scripts\route_task.py` — deterministic, fail-closed planner.

The returned plan selects the required capability evidence and child skill. Do not preload or substitute `routing.json`, a stale capability graph, or model intuition for this chain.

## 7.2 Claude Code

Claude Code is the best fit for directly connecting this package because it supports:

- MCP
- Local hooks
- Project-level instructions
- Local scripts

If you already have `.claude\settings.local.json`, `.claude\mcp.json`, or project instructions, update only their non-destructive pointers to the three-step entry chain. Do not copy the full genome into global configuration.

## 7.3 Codex CLI

Codex CLI can also reuse this package, but treat this README as an “integration principle" rather than a guide for one fixed configuration format.

For Codex CLI, ensure at least:

- The AIGX protocol, RULES bootstrap, and deterministic router are exposed to the model
- The model runs the router before RE / CTF / packet-capture work
- If anything-analyzer / jshook / idapro need to be called, the client side has corresponding MCP or external tool integration
- If there is no hook mechanism, use project-level instructions / system prompt as a fallback

In other words, Codex CLI should reuse this **routing methodology and tool entry design**, not necessarily replicate Claude’s hook implementation.

## 7.4 Cursor / Cline / Windsurf / Other Code CLIs

These tools can also reuse this package as long as they satisfy two conditions:

1. They support MCP or equivalent external tool integration
2. They support Rules / custom instructions / project-level instruction files

Add a non-destructive project pointer to `<REPO_ROOT>\.aigx\protocol.aigx`, `<REPO_ROOT>\RULES.md`, and `<SKILL_ROOT>\scripts\route_task.py`. Configure MCP addresses separately; do not inject a duplicated rule body into global configuration.

---

## 8. Required Changes After Migration

This is the easiest part to miss.

### 8.1 Absolute Paths

If you change computer, username, or drive letter, check all of the following:

- `<REPO_ROOT>\...`
- `<user directory>\...`
- `D:\APP\IDA\`

### 8.2 IDA Scripts

Pay special attention to:

- `skills\ida-reverse\scripts\start.ps1`
- `skills\ida-reverse\scripts\open.ps1`

At minimum, confirm:

- `IDADIR`
- Actual path of `idalib-mcp.exe` / `ida-pro-mcp.exe`
- Whether the temporary directory exists and is writable
- Whether port `13337` conflicts

### 8.3 Claude Local Hook

If you have configured Claude with:

- `.claude\settings.local.json`
- `.claude\scripts\route-reverse.ps1`

After migrating the package, update all old paths pointing to:

- `SKILL.md`
- `evolution\SKILL.md`
- `routing.json`
- `routing.md`
- `capability-graph.json`
- `tool-index.md`
- `refresh-tool-index.ps1`

### 8.4 Tool Index

After migration, run again:

```powershell
powershell -File "<SKILL_ROOT>\scripts\refresh-tool-index.ps1"
```

Do not directly trust the bundled `tool-index.md`, because it was scanned on a previous machine.

---

## 9. Recommended Verification Checklist

After installing on a new machine, validate in the following order.

### 9.1 Basic Commands

```powershell
java -version
python --version
pip --version
node -v
npx -v
jadx --version
apktool --version
adb version
frida-ps -U
```

### 9.2 IDA Chain

```powershell
powershell -File "<SKILL_ROOT>\ida-reverse\scripts\start.ps1"
powershell -File "<SKILL_ROOT>\ida-reverse\scripts\open.ps1" -Path "C:\path\to\sample.exe" -TimeoutSeconds 600
```

### 9.3 Tool Index

```powershell
powershell -File "<SKILL_ROOT>\scripts\refresh-tool-index.ps1"
```

Then confirm that `tool-index.md` correctly reflects at least:

- `jadx`
- `apktool`
- `adb`
- `frida`
- `node`
- `npx`
- `jshookmcp`
- `r2` / `rabin2` (if radare2 is installed)

### 9.4 MCP Availability

Confirm that your AI client can see at least:

- anything-analyzer (if integrated)
- jshook (if registered)
- idapro (if integrated and started)

---

## 10. FAQ

### Q1: Can I put `skills` on another drive?

Yes, but you must update every absolute path that references it, including:

- Claude hooks
- Local script paths in MCP example configurations
- Rules / RULES.md / memory pointers you wrote yourself
- Any PowerShell scripts that hard-code old paths

### Q2: Why do documents or scripts still contain `<user directory>\...`?

These are historical example paths from a previous machine. They do not mean you must use those paths. During migration, always use the real paths on your current machine.

### Q3: `tool-index.md` says `yes`; why still can’t Claude call the tool?

Because it only means the **local machine has the executable or runtime conditions**. It does not mean that the corresponding tool or MCP server has been registered in the AI client.

Typical examples:

- `jshookmcp = yes` only means `node/npx` exists
- It does not mean `@jshookmcp/jshook` has been configured in Claude MCP

### Q4: Is IDA required?

No. Binary analysis can start with `radare2`. But if you need stronger pseudocode, xrefs, renaming, and type recovery, IDA remains the deep-analysis option in this package.

### Q5: What is the difference between anything-analyzer and jshookmcp?

- anything-analyzer: more focused on browser automation, HTTP capture, and request analysis
- jshookmcp: more focused on JS runtime, CDP, Hook, SourceMap, and AST
- `js-reverse`: not a tool, but a methodology and workflow

Correct relationship:

- The `playbook` decides how to do it
- anything-analyzer / jshookmcp perform evidence collection and sampling

---

## 11. Suggestions for Distributors

If you plan to distribute this package to others, include:

1. This README
2. An example `mcp.json` with paths already adjusted
3. An example Claude hook with paths already adjusted
4. A “first installation checklist"
5. A freshly scanned `tool-index.md` and `capability-graph.json`

The ideal distribution form is:

- Documents describe only structure and requirements
- Specific machine paths are left for the installer to fill in
- Secrets such as tokens, private URLs, and internal ports are replaced with placeholders

---

## 12. Most Important Files in This Package

If you only read the core files, read these first:

1. `<REPO_ROOT>\README.md`
2. `<REPO_ROOT>\.aigx\protocol.aigx` + concern genomes — canonical project context
3. `<REPO_ROOT>\RULES.md` — compatibility bootstrap into AIGX and the router
4. `<SKILL_ROOT>\SKILL.md` — main controller entry point
5. `<SKILL_ROOT>\evolution\SKILL.md` — GOAL, capability graph, TraceCard, promotion gate
6. `<SKILL_ROOT>\routing.json` + `<SKILL_ROOT>\routing.md` — scenario → skill dispatch
7. `<SKILL_ROOT>\capability-graph.json` + `<SKILL_ROOT>\tool-index.md` — local capability/tool status

If a security route is blocked on authorization, provide an explicit current-session `authorization_scope` or stop. Package precedents are generic methodology; they cannot override a refusal, establish target ownership, or replace the router's authorization gate.

If adding a new skill, read:

9. `<SKILL_ROOT>\CONTRIBUTING.md`

---

## 13. Context Bootstrap Across AI Clients

The canonical rule source is `.aigx/`. `RULES.md` and client-specific instruction files are thin, non-destructive pointers into that context; they must not copy the full rule set or silently mutate global client configuration.

### 13.1 First-Use Flow

1. Open `<REPO_ROOT>` in the AI client.
2. Have the client read `.aigx\protocol.aigx` and `RULES.md`.
3. Run the deterministic router with the task and its actual artifact or project path.
4. Continue only on `status=ready`; treat missing artifact input, invalid AIGX, unresolved edit boundaries, and failed structural gates as blockers.

### 13.2 Verify the Bootstrap

For an artifact route, omit `--input-path` once and confirm the router returns `status=blocked` with `input_path_required`. Then provide an existing file and confirm the plan reports the selected controlled entrypoint. This verification does not modify the artifact, IDA configuration, or a structural baseline.

### 13.3 Updates

Update the relevant AIGX concern and its indexed implementation/documentation together. Run official AIGX lint, targeted route tests, and the full script regression suite before promotion.

---

## 14. Session Context

Keep machine state, target paths, credentials, contracts, IDB files, and run artifacts outside this repository. AIGX stores stable project rules and file boundaries; it is not a registry of analyzed targets or a replacement for per-session authorization.

---

## 15. Auto-Evolution Without Target Persistence

Runtime traces, reports, target identifiers, paths, binaries, source facts, IDBs, commands containing target data, and analysis evidence stay in the authorized target workspace or an external session store. Completing a task does **not** automatically write anything into this distribution repository.

### 15.1 Promotion Candidate

Only a generic pattern may be proposed for promotion. Before it enters this repository, it must be anonymized, independent of one target, covered by a reproducible fixture or regression test, tied to a success oracle, and supplied with rollback evidence. A candidate that cannot satisfy these properties remains external.

### 15.2 Promotion Gate

Use `evolution/trace-card.template.yaml` and `evolution/promotion-record.template.yaml`. The states remain strict:

- `validated`: the generic oracle and regression pass; the pattern may influence routing.
- `candidate`: potentially reusable but not regression-proven; advisory only.
- `forensic`: failure, anomaly, suspected contamination, or target-specific evidence; analysis only and never promoted into control flow.

Only an explicit, reviewed promotion may update AIGX, `routing.md`, `routing.json`, a child skill, or `bootstrap-manifest.json`. Run the official AIGX lint, targeted regression, full script suite, and sensitive-data scan before commit.

### 15.3 Shipped Field Journal

`field-journal/` contains package-owned generic precedents and previously promoted patterns. It is not a per-project log directory, authorization database, or destination for automatic session write-back.

---

## 16. Complete Behavior Summary for the AI

The canonical sequence is: load AIGX → resolve the task and edit boundaries → build the deterministic route → satisfy input, capability, service, authorization, and project gates → execute the controlled workflow → verify its success oracle → promote only generic, regression-backed learning. `RULES.md` is only the compatibility entry to this sequence.

---

Finally, recommendations:

- Treat this package as a "skill routing + tool entry + methodology asset + self-evolving knowledge base," not as a manual for a single client.
- The real sign of successful migration is not that “the files were copied," but that every supported client follows the same AIGX-first route, calls capabilities that actually exist, keeps target evidence external, and promotes only reviewed generic learning.

---

## 17. User Guidance When Bootstrap Fails

Not every capability can be installed automatically with 100% success. When the AI tries to auto-complete installation and still fails, it **must not stay silent or retry endlessly**. It must immediately switch to “guide the user to configure manually" mode.

### 17.1 AI Failure-Handling Flow

```text
1. Call bootstrap-reverse.ps1 to attempt automatic installation
2. Verify whether the tool is usable after installation
3. If it is still unavailable → do not retry → immediately output structured guidance
```

### 17.2 Structured Guidance Template

When automatic installation fails, the AI must tell the user in the following format:

```markdown
⚠️ **[Tool Name] automatic installation failed. Manual action is required.**

**Problem**: [Specific error message]

**Possible causes**:
- [Cause 1, e.g. network unavailable / GitHub API rate limit]
- [Cause 2, e.g. missing prerequisite]
- [Cause 3, e.g. port already in use]

**Manual installation steps**:
1. [Step 1, including concrete command or download link]
2. [Step 2]
3. [Step 3]

**Verify after installation**:
```
[verification command]
```

**After verification succeeds, tell me and I will continue the current task.**
```

### 17.3 Concrete Guidance for Each Capability

#### anything-analyzer Installation Failure or Port Mismatch

```markdown
⚠️ **anything-analyzer service unavailable**

**Problem**: Port 23816 does not respond, or the service is not started

**Possible causes**:
- Project has not been cloned locally
- pnpm is not installed
- Port is occupied by another program
- Project dependencies are not installed

**Manual installation steps**:

1. Ensure Node.js and pnpm are installed:
   ```powershell
   node -v          # Requires v18+
   pnpm -v          # If missing: npm install -g pnpm
   ```

2. Clone the project:
   ```powershell
   git clone https://github.com/Mouseww/anything-analyzer.git C:\work\anything-analyzer
   cd C:\work\anything-analyzer
   ```

3. Install dependencies and start:
   ```powershell
   pnpm install
   pnpm dev
   ```

4. After the service starts, check the port:
   ```powershell
   curl http://localhost:23816/mcp
   ```
   If the port is not 23816, tell me the actual port number and I will help update the MCP configuration.

5. Register it in your AI client MCP configuration:
   ```json
   {
     "mcpServers": {
       "anything-analyzer": {
         "url": "http://localhost:23816/mcp"
       }
     }
   }
   ```
   - Claude Code: write to `~/.claude/mcp.json`
   - Kiro: write to `.kiro/settings/mcp.json`
   - Cursor: add it in the MCP settings panel

**After verification succeeds, tell me and I will continue the current task.**
```

#### jshookmcp Registration Failure or Uncallable Server

```markdown
⚠️ **jshookmcp MCP server unavailable**

**Problem**: Registered but cannot be called, or registration failed

**Possible causes**:
- `npx` cannot fetch the `@jshookmcp/jshook` package because of network issues
- The MCP client has not enabled this server
- Node.js version is too old

**Manual configuration steps**:

1. Confirm `npx` works:
   ```powershell
   npx -v    # Requires 9.0+
   ```

2. Test whether the package can be fetched:
   ```powershell
   npx -y @jshookmcp/jshook@latest --help
   ```

3. Add this to MCP configuration:
   ```json
   {
     "mcpServers": {
       "jshook": {
         "command": "npx",
         "args": ["-y", "@jshookmcp/jshook@latest"],
         "env": {
           "JSHOOK_BASE_PROFILE": "search"
         }
       }
     }
   }
   ```

4. Restart the AI client or reconnect the MCP server

**After configuration is complete, tell me and I will continue the current task.**
```

#### idalib-mcp / IDA Pro Service Startup Failure

```markdown
⚠️ **IDA Pro MCP service unavailable**

**Problem**: Port 13337 does not respond

**Possible causes**:
- IDA Pro is not installed or `IDADIR` is not set
- idalib-mcp is not installed
- IDA license issue

**Manual configuration steps**:

1. Confirm IDA Pro is installed and note its installation directory

2. Set environment variable (replace with your real path):
   ```powershell
   [Environment]::SetEnvironmentVariable('IDADIR', '<your IDA installation directory>', 'User')
   ```
   Or CMD:
   ```cmd
   setx IDADIR "<your IDA installation directory>"
   ```

3. Install ida-pro-mcp (must be from GitHub, not PyPI):
   ```powershell
   pip install git+https://github.com/mrexodia/ida-pro-mcp.git
   ```

4. Install the IDA plugin:
   ```powershell
   ida-pro-mcp --install
   ```
   Choose: Streamable HTTP → Global → select all clients

5. Restart IDA Pro, open the target file, and the plugin will automatically listen on 13337

**After startup succeeds, tell me and I will continue the current task.**
```

#### radare2 Installation Failure

```markdown
⚠️ **radare2 automatic installation failed**

**Problem**: GitHub Release download failed or PATH was not updated after extraction

**Manual installation steps**:

1. Download the latest Windows version from GitHub:
   https://github.com/radareorg/radare2/releases
   Choose `radare2-*-w64.zip`

2. Extract it to: `C:\Users\<your username>\Tools\radare2\`

3. Add the `bin\` directory to system PATH:
   ```powershell
   $r2bin = "$env:USERPROFILE\Tools\radare2\bin"
   [Environment]::SetEnvironmentVariable('PATH', "$r2bin;$([Environment]::GetEnvironmentVariable('PATH', 'User'))", 'User')
   ```

4. Open a new terminal and verify:
   ```powershell
   r2 -v
   rabin2 -v
   ```

**Tell me after verification succeeds.**
```

#### zipalign / apksigner Unavailable

```markdown
⚠️ **Android Build-Tools not installed (`zipalign` / `apksigner` unavailable)**

**Note**: These two tools cannot currently be fully auto-installed. They must be handled manually through Android SDK Manager.

**Manual installation steps**:

1. If Android Studio is installed, open SDK Manager and install Build-Tools

2. If you only want command-line installation:
   ```powershell
   # First confirm the location of sdkmanager, usually under the Android SDK cmdline-tools directory
   sdkmanager "build-tools;35.0.0"
   ```

3. After installation, confirm the paths exist:
   ```powershell
   dir "$env:LOCALAPPDATA\Android\Sdk\build-tools\35.0.0\zipalign.exe"
   dir "$env:LOCALAPPDATA\Android\Sdk\build-tools\35.0.0\apksigner.bat"
   ```

4. You do not need to manually add them to PATH. This package’s scripts will automatically scan the build-tools directory.

**After installation, run `refresh-tool-index.ps1` to refresh the index.**
```

### 17.4 Port Conflict Handling

When the MCP service port is different from the expected one, the AI should:

1. Ask the user for the actual port number
2. Help update the URL in the MCP configuration
3. Update the corresponding `servicePort` in `bootstrap-manifest.json` if it is a permanent change
4. Re-verify connectivity

Example dialogue:

```text
AI: The default anything-analyzer port 23816 is not responding. Which port is your service running on?
User: 3000
AI: Got it. I will update the MCP configuration to http://localhost:3000/mcp and verify connectivity.
```

### 17.5 Summary of AI Behavior Rules

| Situation | What the AI Should Do |
|-----------|------------------------|
| Bootstrap succeeds | Continue the task without bothering the user |
| Bootstrap fails with a clear cause | Output structured guidance and wait for user confirmation before continuing |
| Bootstrap fails for an unknown reason | Output known information + suggest checking network/permissions, then wait for confirmation |
| Service port mismatch | Ask for the actual port and help update configuration |
| Repeated failure (same tool fails twice) | Clearly state that automatic installation cannot complete, provide full manual steps, and stop retrying |
| User confirms manual installation | Re-run `refresh-tool-index.ps1` to verify, then continue the task |

---

## 18. License and Disclaimer

This package is intended only for legally authorized security research, learning, and CTF competitions.

- Users must ensure all operations are within legal boundaries
- Unauthorized penetration testing against other people’s systems is illegal
- The package author is not responsible for misuse
- Reverse engineering should comply with local laws, regulations, and software license agreements
- Operations in CTF competition environments should not be extended beyond the competition scope

---

Final recommendation:

- Treat this package as a "skill routing + tool entry + methodology asset + self-evolving knowledge base," not as the manual for a single client.
- A successful migration is not proven by “files copied successfully." It is proven when any supported code CLI follows the same AIGX-first route, calls capabilities that actually exist on the machine, keeps target evidence external, and promotes only reviewed generic learning.
