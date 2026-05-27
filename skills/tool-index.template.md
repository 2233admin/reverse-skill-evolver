# Reverse Engineering Tool Index

> **This file is a TEMPLATE.** Run `refresh-tool-index.ps1` (Windows) or `refresh-tool-index.sh` (Linux) to generate the actual `tool-index.md`, `tool-index.json`, and `capability-graph.json` with your machine's real paths, versions, MCP/service state, and smoke status.
>
> - Scan time: (auto-generated)
> - Routing entry: `SKILL.md` → `routing.md` → corresponding sub-skill
> - Note: For MCP servers like jshookmcp, `yes` only means the local machine has the runtime (node/npx), NOT that it's registered and enabled in your AI client.
> - **IMPORTANT**: All paths MUST be complete absolute paths (e.g., `D:\wangluo\jadx\bin\jadx.bat`). Never write just the tool name. Include version, full path, and verification command. This is the shared registry that ALL CLI clients rely on.
> - `capability-graph.json` is the session-level graph used by `evolution/SKILL.md` before routing. It includes tool nodes, MCP/service status, memory policy, and promotion-gate requirements.

## Tool Availability Table

| Tool | Skill | Purpose | Available | Path | Version | Source | Script Reference |
|------|-------|---------|-----------|------|---------|--------|-----------------|
| jadx | apk-reverse | Java decompiler | — | — | — | — | apk-reverse/scripts/decode.ps1 |
| apktool | apk-reverse | APK unpack & rebuild | — | — | — | — | apk-reverse/scripts/decode.ps1 |
| adb | apk-reverse | Device connection & logcat | — | — | — | — | apk-reverse/scripts/rebuild-sign-install.ps1 |
| java | apk-reverse | Run jar & Java toolchain | — | — | — | — | apk-reverse/scripts/decode.ps1 |
| apksigner | apk-reverse | APK signing | — | — | — | — | apk-reverse/scripts/rebuild-sign-install.ps1 |
| zipalign | apk-reverse | APK alignment | — | — | — | — | apk-reverse/scripts/rebuild-sign-install.ps1 |
| frida | apk-reverse | Frida dynamic injection | — | — | — | — | apk-reverse/scripts/frida-run.ps1 |
| frida-ps | apk-reverse | Frida process enumeration | — | — | — | — | apk-reverse/scripts/frida-run.ps1 |
| r2 | radare2 | radare2 main analyzer | — | — | — | — | radare2/scripts/recon.ps1 |
| rabin2 | radare2 | Binary recon | — | — | — | — | radare2/scripts/recon.ps1 |
| rasm2 | radare2 | Assemble/disassemble | — | — | — | — | radare2/SKILL.md |
| radiff2 | radare2 | Binary diff | — | — | — | — | radare2/SKILL.md |
| python | reverse-engineering | Script execution | — | — | — | — | — |
| pip | reverse-engineering | Python package manager | — | — | — | — | — |
| node | js-reverse | Node.js runtime & MCP | — | — | — | — | js-reverse/SKILL.md |
| npx | js-reverse | Run temp npm packages | — | — | — | — | js-reverse/SKILL.md |
| jshookmcp | js-reverse | JS Hook MCP (needs MCP client registration) | — | — | — | — | js-reverse/SKILL.md |
| agent-browser | browser-automation | Playwright browser automation | — | — | — | — | browser-automation/SKILL.md |
| playwright | browser-automation | Playwright engine | — | — | — | — | browser-automation/SKILL.md |
| analyzeHeadless | reverse-engineering | Ghidra headless analysis | — | — | — | — | reverse-engineering/SKILL.md |
| proxycat | pentest-tools | Proxy pool management | — | — | — | — | pentest-tools/SKILL.md |
| nmap | pentest-tools | Port scan & service ID | — | — | — | — | pentest-tools/SKILL.md |

---

## Capability Status (MCP Services)

| Capability | Tool Available | MCP Registered | Service Online | Auto-installable | Install Method |
|------------|:---:|:---:|:---:|:---:|----------------|
| jadx | — | — | — | ✓ | github-release-zip |
| apktool | — | — | — | ✓ | github-release-jar-wrapper |
| frida | — | — | — | ✓ | pip-package |
| idalib-mcp | — | — | — | ✓ | pip-package |
| jshookmcp | — | ✓ | — | ✓ | npm-mcp |
| anything-analyzer | — | ✓ | — | ✓ | local-http-mcp |
| idapro | — | ✓ | — | ✓ | local-http-mcp |
| burpsuite-mcp | — | ✓ | — | ✗ | local-http-mcp (manual Burp extension) |
| r2 | — | — | — | ✓ | github-release-zip |
| adb | — | — | — | ✓ | winget-package |
| agent-browser | — | — | — | ✓ | npm-global |
| ghidra-mcp | — | ✓ | — | ✓ | github-release-zip |
| nmap | — | — | — | ✓ | winget-package |
| proxycat | — | — | — | ✓ | git-clone |

> ✓ = Yes | ✗ = No | — = Not scanned yet (run refresh-tool-index to populate)

---

## How to Generate

**Windows:**
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_ROOT>/skills/scripts/refresh-tool-index.ps1"
```

**Linux/Kali:**
```bash
bash <SKILL_ROOT>/kali/scripts/refresh-tool-index.sh
```

After running, this template is replaced by `tool-index.md` with your machine's actual paths, versions, and availability status. The same scan also emits `tool-index.json` and `capability-graph.json`.
