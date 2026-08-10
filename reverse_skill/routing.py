#!/usr/bin/env python3
"""Deterministic task router for reverse-skill-evolver.

The router turns a task description into a checked dispatch plan.  It does not
silently install tools or run security actions.  ``--execute`` is an explicit
opt-in for the small number of workflows that already have a controlled local
entrypoint.

Exit codes:
  0 ready
  2 blocked by capability or authorization gate
  3 no route matched
  4 invalid input or route data
  5 an explicitly requested entrypoint failed
  6 a route has no executable entrypoint yet
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .aigx import inspect_project as inspect_aigx_project, run_aigx_json
from .teams_preflight import find_git_ida


EXIT_READY = 0
EXIT_BLOCKED = 2
EXIT_NO_ROUTE = 3
EXIT_INVALID = 4
EXIT_EXECUTION_FAILED = 5
EXIT_NO_ENTRYPOINT = 6

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
SKILLS_ROOT = REPO_ROOT / "skills"
DATA_ROOT = PACKAGE_ROOT / "data"
ROUTING_PATH = SKILLS_ROOT / "routing.json" if (SKILLS_ROOT / "routing.json").is_file() else DATA_ROOT / "routing.json"
TOOL_INDEX_PATH = SKILLS_ROOT / "tool-index.json"
CAPABILITY_GRAPH_PATH = SKILLS_ROOT / "capability-graph.json"
IDA_GRAPH_PATH = SKILLS_ROOT / "generated" / "ida-capability-graph.json"
_MCP_TOOL_CACHE: Dict[int, Optional[set[str]]] = {}
DEFAULT_CODE_INTEL_ARTIFACT_ROOT = Path(
    os.environ.get("CODE_INTEL_ARTIFACT_ROOT")
    or Path(os.environ.get("LOCALAPPDATA", "")) / "code-intel" / "artifacts"
)

AUTHORIZED_SCOPE_KINDS = {
    "ctf",
    "own_asset",
    "lab_fixture",
    "bug_bounty",
    "engagement",
}

SECURITY_ROUTE_IDS = {
    "active-security-assessment",
    "api-security",
    "firmware-pentest",
    "llm-security",
    "patch-diff-exploit",
    "pwn-chain",
    "attack-chain",
    "edr-bypass-re",
}

SECURITY_WORDS = (
    "pentest",
    "渗透",
    "exploit",
    "利用",
    "payload",
    "提权",
    "lateral",
    "横向",
    "bypass",
    "绕过",
    "brute force",
    "爆破",
    "pwn",
    "漏洞利用",
)

ROUTE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "apk-android": (
        "apk",
        "android",
        "安卓",
        "smali",
        "jadx",
        "apktool",
        "ssl pinning",
        "root detection",
    ),
    "js-browser-signature": (
        "javascript",
        "js",
        "前端",
        "浏览器",
        "签名",
        "加密参数",
        "websocket",
        "sourcemap",
        "cdp",
    ),
    "native-binary": (
        "binary",
        "二进制",
        "exe",
        "dll",
        "sys",
        "elf",
        "so",
        "macho",
        "反编译",
        "反汇编",
        "ida",
        "xref",
        "pathfinder",
        "dyld",
        "git-ida",
        "ida teams",
    ),
    "patch-diff": (
        "diff",
        "差分",
        "bindiff",
        "diaphora",
        "补丁",
        "patch diff",
        "cve reproduction",
        "符号迁移",
    ),
    "protocol-pcap": (
        "pcap",
        "pcapng",
        "抓包",
        "协议逆向",
        "数据包",
        "packet",
        "wireshark",
        "tshark",
    ),
    "protocol-source-implementation": (
        "协议实现",
        "协议源码",
        "codec",
        "packet parser",
        "fixture replay",
        "cargo test",
        "rust workspace",
        "go workspace",
    ),
    "mobile-reverse": ("mobile", "移动端", "ios", "ipa", "objection"),
    "firmware-pentest": ("firmware", "固件", "iot", "路由器固件", "qemu", "afl++"),
    "malware-analysis": ("malware", "恶意软件", "病毒", "样本分析", "ioc", "sigma", "sandbox"),
    "api-security": ("api security", "api 安全", "graphql", "jwt", "oauth", "bola", "idor"),
    "llm-security": ("llm security", "llm 安全", "prompt injection", "提示词注入", "agent security", "模型安全"),
    "supply-chain-security": ("supply chain", "供应链", "sbom", "sca", "依赖扫描", "trivy"),
    "pwn-chain": ("pwn", "rop", "ret2libc", "栈溢出", "堆利用", "pwntools"),
    "ghidra-reverse": ("ghidra", "ghidra headless"),
    "edr-bypass-re": ("edr", "edr bypass", "av bypass", "amsi", "etw", "edr 绕过"),
    "diagram-generator": ("diagram", "图表", "流程图", "架构图", "状态机"),
    "docs-generator": ("report", "报告", "writeup", "文档", "技术报告"),
    "architecture-governance": ("sentrux", "architecture health", "structural gate", "architecture check", "架构门禁", "结构质量"),
    "active-security-assessment": (
        "security assessment",
        "安全测试",
        "渗透测试",
        "bug bounty",
        "漏洞扫描",
        "api security",
        "graphql",
        "jwt",
        "nuclei",
        "burp",
    ),
    "unattended-overnight-run": (
        "overnight",
        "过夜",
        "整夜",
        "无人值守",
        "unattended",
        "deadline",
        "早上看结果",
    ),
    "workspace-search": (
        "workspace search",
        "code search",
        "search files",
        "ripgrep",
        "xcmd",
        "x rg",
        "搜索代码",
        "搜索工作区",
    ),
}

TARGET_ALIASES: Dict[str, Tuple[str, ...]] = {
    "apk-android": ("apk", "android", "xapk", "dex", "smali", "安卓"),
    "js-browser-signature": ("js_bundle", "javascript", "web_frontend", "browser_runtime", "sourcemap", "网页", "前端"),
    "native-binary": ("elf", "pe", "dll", "so", "macho", "stripped_binary", "exe", "sys", "二进制"),
    "patch-diff": ("two_versions", "vendor_patch", "nday", "cve_reproduction", "补丁", "差分"),
    "protocol-pcap": ("pcap", "custom_protocol", "packet_capture", "websocket_capture", "抓包"),
    "protocol-source-implementation": ("source_tree", "rust_workspace", "go_workspace", "custom_protocol_client", "market_data_protocol", "源码", "协议源码"),
    "mobile-reverse": ("ipa", "ios", "mobile_app", "移动端", "iOS"),
    "firmware-pentest": ("firmware", "iot", "固件", "router_firmware"),
    "malware-analysis": ("malware", "virus_sample", "恶意样本", "病毒样本"),
    "api-security": ("api", "web_api", "graphql", "jwt", "api_security", "API安全"),
    "llm-security": ("llm_application", "agent_surface", "prompt_injection", "LLM安全"),
    "supply-chain-security": ("supply_chain", "sbom", "sca", "供应链安全"),
    "pwn-chain": ("pwn", "rop", "exploit_chain", "利用链"),
    "ghidra-reverse": ("ghidra", "ghidra_headless"),
    "edr-bypass-re": ("edr", "av_bypass", "edr_bypass"),
    "diagram-generator": ("diagram", "flowchart", "architecture_diagram", "图表"),
    "docs-generator": ("report", "writeup", "technical_report", "报告"),
    "architecture-governance": ("source_tree", "architecture_governance", "codebase", "源码项目", "架构治理"),
    "active-security-assessment": ("web_app", "api", "cloud", "network", "source_tree", "安全测试"),
    "unattended-overnight-run": ("overnight_run", "unattended_task", "deadline_run", "过夜"),
    "workspace-search": ("workspace_search", "source_search", "code_search", "代码搜索", "工作区搜索"),
}

FALLBACK_CAPABILITIES: Dict[str, Tuple[str, ...]] = {
    "radare2": ("rabin2",),
    "reverse-engineering": ("python",),
    "pwn-chain": ("python",),
    "ida-reverse": ("idapro",),
    "jshookmcp": ("jshookmcp",),
    "patch-diff-exploit": ("python",),
    "browser-automation": ("agent-browser", "playwright"),
    "js-reverse": ("node", "npx"),
    "apk-reverse": ("java",),
}


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def bounded_text(value: str, limit: int = 600) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized[:limit]


def run_readonly_command(command: Sequence[str], cwd: Path, timeout_seconds: int = 30) -> Dict[str, Any]:
    """Run a local analysis command without leaking its full output into routing JSON."""
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        return {"returncode": completed.returncode, "summary": bounded_text(combined)}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"returncode": None, "summary": bounded_text(str(error))}


def sentrux_cli_state() -> Dict[str, Any]:
    """Discover the native Sentrux CLI without assuming Code Intel is installed."""
    command = shutil.which("sentrux")
    if not command:
        return {"status": "unavailable", "reason": "sentrux_not_on_path"}
    version = run_readonly_command([command, "--version"], REPO_ROOT, timeout_seconds=5)
    return {
        "status": "available" if version.get("returncode") == 0 else "unavailable",
        "path": command,
        "version": version.get("summary", ""),
        "version_exit_code": version.get("returncode"),
        "mcp_launch": [command, "mcp"],
        "mcp_registration": "explicit_host_registration_required",
    }


def parse_sentrux_observation(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize Sentrux's human-oriented check output into stable route parameters."""
    text = str(result.get("summary", ""))
    files = re.search(r"\[build_graphs\]\s+(\d+)\s+files\b.*?\|\s+(\d+)\s+import,\s+(\d+)\s+call", text)
    resolved = re.search(r"\[resolve\]\s+(\d+)\s+resolved,\s+(\d+)\s+unresolved", text)
    rules_missing = "No .sentrux/rules.toml found" in text
    baseline_missing = "Sentrux baseline missing" in text or "Failed to load baseline" in text
    observed = bool(result.get("returncode") == 0 or files or resolved or rules_missing or baseline_missing)
    rules = "missing" if rules_missing else ("present" if result.get("returncode") == 0 else "unknown")
    baseline = "missing" if baseline_missing else ("present" if result.get("returncode") == 0 else "unknown")
    observation: Dict[str, Any] = {
        "status": "observed" if observed else "unavailable",
        "ready": result.get("returncode") == 0,
        "exit_code": result.get("returncode"),
        "rules": rules,
        "baseline": baseline,
        "summary": bounded_text(text),
    }
    if files:
        observation["graph"] = {
            "files": int(files.group(1)),
            "imports": int(files.group(2)),
            "calls": int(files.group(3)),
        }
    if resolved:
        observation["resolution"] = {
            "resolved": int(resolved.group(1)),
            "unresolved": int(resolved.group(2)),
        }
    return observation


def resolve_sentrux_scope(
    project: Path,
    aigx: Dict[str, Any],
    runner=None,
) -> Dict[str, Any]:
    """Resolve one project-owned Sentrux scope through official AIGX boundaries."""
    project = project.resolve()
    runner = runner or run_aigx_json
    command = str((aigx.get("validator") or {}).get("path") or "")
    if not command:
        return {
            "status": "blocked",
            "ready": False,
            "reason": "aigx_validator_unavailable",
        }

    scopes: List[Path] = []
    for rules_path in sorted(project.rglob("rules.toml")):
        if rules_path.parent.name != ".sentrux":
            continue
        scope = rules_path.parent.parent.resolve()
        try:
            scope.relative_to(project)
        except ValueError:
            continue
        if scope not in scopes:
            scopes.append(scope)

    if not scopes:
        return {
            "status": "blocked",
            "ready": False,
            "reason": "sentrux_scope_missing",
            "candidates": [],
        }

    governed: List[Tuple[Path, Dict[str, Any], str]] = []
    for scope in scopes:
        sentrux_dir = scope / ".sentrux"
        for boundary_path in (sentrux_dir / "baseline.json", sentrux_dir / "rules.toml"):
            if not boundary_path.is_file():
                continue
            relative = boundary_path.relative_to(project).as_posix()
            resolved = runner(
                command,
                ["--root", str(project), "--resolve", relative, "--format", "json"],
                project,
            )
            data = resolved.get("data") if isinstance(resolved.get("data"), dict) else {}
            if (
                resolved.get("returncode") == 0
                and data.get("found")
                and data.get("domain") == "architecture-governance"
            ):
                governed.append((scope, data, relative))
                break

    candidates = ["." if scope == project else scope.relative_to(project).as_posix() for scope in scopes]
    if not governed:
        return {
            "status": "blocked",
            "ready": False,
            "reason": "sentrux_scope_unresolved",
            "candidates": candidates,
        }
    if len(governed) != 1:
        return {
            "status": "blocked",
            "ready": False,
            "reason": "sentrux_scope_ambiguous",
            "candidates": candidates,
            "governed": [
                "." if scope == project else scope.relative_to(project).as_posix()
                for scope, _boundary, _relative in governed
            ],
        }

    scope, boundary, boundary_path = governed[0]
    return {
        "status": "ready",
        "ready": True,
        "path": str(scope),
        "relative": "." if scope == project else scope.relative_to(project).as_posix(),
        "source": "aigx_architecture_governance_boundary",
        "boundary_path": boundary_path,
        "checks": as_list(boundary.get("checks")),
    }


def latest_legacy_sentrux_hotspots(artifact_root: Path, project_name: str) -> Dict[str, Any]:
    """Expose same-project legacy Sentrux data as advisory, never as current facts."""
    project_root = artifact_root / project_name
    if not project_root.is_dir():
        return {"status": "not_found"}
    for run_dir in sorted((path for path in project_root.iterdir() if path.is_dir()), reverse=True):
        hotspot_path = run_dir / "sentrux-hotspots.json"
        if not hotspot_path.is_file():
            continue
        try:
            document = read_json(hotspot_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        modules = [
            {"name": item.get("name"), "risk": item.get("riskScore", item.get("risk"))}
            for item in as_list(document.get("modules"))
            if isinstance(item, dict) and item.get("name")
        ]
        return {
            "status": "candidate",
            "run": run_dir.name,
            "source": "legacy_sentrux_hotspots",
            "top_modules": modules[:5],
            "policy": "advisory_only_until_current_project_oracle_passes",
        }
    return {"status": "not_found"}


def collect_project_intelligence(
    project_path: str,
    aigx_targets: Sequence[str] = (),
    aigx_command: Optional[str] = None,
) -> Dict[str, Any]:
    """Collect mandatory AIGX context plus derived project intelligence."""
    project = Path(project_path).expanduser()
    if not project.is_dir():
        return {
            "status": "invalid",
            "project_path": str(project),
            "reason": "project_path_not_found",
            "aigx": {"status": "blocked", "ready": False, "reason": "project_path_not_found"},
        }

    project = project.resolve()
    project_name = project.name
    aigx = inspect_aigx_project(str(project), aigx_targets, aigx_command)
    result: Dict[str, Any] = {
        "status": "observed" if aigx.get("ready") else "blocked",
        "project_path": str(project),
        "project_name": project_name,
        "evidence_scope": "current_project_only",
        "cross_project_memory": "generic_patterns_only; never import another project's structural facts",
        "aigx": aigx,
        "code_intel": {"status": "not_run", "reason": "aigx_gate_not_ready"},
        "sentrux": {"status": "not_run", "reason": "aigx_gate_not_ready"},
        "legacy_sentrux_history": {"status": "not_run", "reason": "aigx_gate_not_ready"},
    }
    if not aigx.get("ready"):
        return result

    code_intel = shutil.which("code-intel")
    sentrux_scope = resolve_sentrux_scope(project, aigx)
    result["code_intel"] = {"status": "unavailable", "reason": "code_intel_not_on_path"}
    result["sentrux"] = {
        "status": "not_run",
        "ready": False,
        "reason": (
            sentrux_scope.get("reason")
            if not sentrux_scope.get("ready")
            else "code_intel_not_on_path"
        ),
        "scope": sentrux_scope,
    }
    result["legacy_sentrux_history"] = latest_legacy_sentrux_hotspots(
        DEFAULT_CODE_INTEL_ARTIFACT_ROOT, project_name
    )
    if code_intel:
        artifact_result = run_readonly_command(
            [
                code_intel,
                "artifact",
                "query",
                "--artifact-root",
                str(DEFAULT_CODE_INTEL_ARTIFACT_ROOT),
                "--repo",
                project_name,
                "--type",
                "code_evidence.agent_slice",
            ],
            project,
        )
        result["code_intel"] = {
            "status": "authoritative" if artifact_result["returncode"] == 0 else "unavailable",
            "summary": artifact_result["summary"],
            "artifact_root": str(DEFAULT_CODE_INTEL_ARTIFACT_ROOT),
        }

    if code_intel and sentrux_scope.get("ready"):
        command = [code_intel, "sentrux", "check", str(sentrux_scope["path"])]
        gate = parse_sentrux_observation(run_readonly_command(command, project))
        gate.update(
            {
                "scope": sentrux_scope,
                "rules": gate["rules"],
                "baseline": gate["baseline"],
                "graph": gate.get("graph"),
                "resolution": gate.get("resolution"),
                "commands": {
                    "check": command,
                    "save_baseline_policy": "never_automatic; explicit_project_workflow_only",
                },
            }
        )
        result["sentrux"] = gate
    return result


def normalize(value: Any) -> str:
    text = str(value or "").casefold()
    return re.sub(r"\s+", " ", text).strip()


def compact(value: Any) -> str:
    return re.sub(r"[^\w\u0080-\uffff]+", "", normalize(value))


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def task_text(task: Dict[str, Any]) -> str:
    fields = [
        task.get("task"),
        task.get("intent"),
        task.get("target_kind"),
        task.get("mode"),
        task.get("toolchain"),
        task.get("evidence"),
        task.get("input_path"),
    ]
    return " ".join(str(item) for item in fields if item is not None)


def contains_keyword(text: str, keyword: str) -> bool:
    needle = normalize(keyword)
    haystack = normalize(text)
    if not needle:
        return False
    if re.fullmatch(r"[a-z0-9_ .+/-]+", needle):
        pattern = rf"(?<![a-z0-9_]){re.escape(needle)}(?![a-z0-9_])"
        return re.search(pattern, haystack) is not None
    if needle in haystack:
        return True
    return compact(needle) in compact(haystack)


def is_ida_teams_task(task: Dict[str, Any]) -> bool:
    """Identify the explicit IDA Teams Git-backend workflow."""
    text = task_text(task)
    return any(
        contains_keyword(text, term)
        for term in ("ida teams", "git-ida", "teams collaboration", "teams worktree", "团队协作", "隔离 worktree")
    )


def is_teams_worktree_task(task: Dict[str, Any]) -> bool:
    """Identify the source-isolation stage before any IDA Teams setup."""
    text = task_text(task)
    return any(contains_keyword(text, term) for term in ("teams worktree", "隔离 worktree"))


def is_teams_artifact_analysis_task(task: Dict[str, Any]) -> bool:
    """Detect an unsupported composite of Teams setup and binary analysis."""
    if task.get("input_path"):
        return True
    text = task_text(task)
    return any(
        contains_keyword(text, term)
        for term in (
            "analyze this",
            "analyze the binary",
            "static analysis",
            "dynamic analysis",
            "decompile",
            "disassemble",
            "control flow",
            "function labeling",
            "xref",
            "分析这个",
            "分析该",
            "静态分析",
            "动态分析",
            "反编译",
            "反汇编",
            "控制流",
            "函数标注",
            "交叉引用",
        )
    )


def is_workspace_search_task(task: Dict[str, Any]) -> bool:
    """Identify a bounded, read-only source/workspace search request."""
    if normalize(task.get("target_kind")) in {"workspace-search", "workspace_search", "source_search", "code_search"}:
        return True
    text = task_text(task)
    return any(
        contains_keyword(text, term)
        for term in ("workspace search", "code search", "search files", "ripgrep", "xcmd", "x rg", "搜索代码", "搜索工作区")
    )


def has_explicit_token(text: str, token: str) -> bool:
    """Match an ASCII tool/token without treating it as a substring of a word."""
    needle = normalize(token)
    haystack = normalize(text)
    if not needle:
        return False
    if re.fullmatch(r"[a-z0-9_ .+/-]+", needle):
        pattern = rf"(?<![a-z0-9_]){re.escape(needle)}(?![a-z0-9_])"
        return re.search(pattern, haystack) is not None
    return contains_keyword(haystack, needle)


def infer_target_kind(task: Dict[str, Any]) -> str:
    explicit = normalize(task.get("target_kind"))
    if explicit:
        architecture_terms = ROUTE_ALIASES["architecture-governance"]
        if explicit in {"source_tree", "codebase", "architecture_governance"} and any(
            contains_keyword(task_text(task), term) for term in architecture_terms
        ):
            return "architecture-governance"
        for canonical, aliases in TARGET_ALIASES.items():
            if explicit == canonical or explicit in {normalize(item) for item in aliases}:
                return canonical
        return explicit

    input_path = str(task.get("input_path") or "")
    suffix = Path(input_path).suffix.casefold()
    suffix_map = {
        ".apk": "apk-android",
        ".xapk": "apk-android",
        ".dex": "apk-android",
        ".smali": "apk-android",
        ".js": "js-browser-signature",
        ".mjs": "js-browser-signature",
        ".cjs": "js-browser-signature",
        ".map": "js-browser-signature",
        ".exe": "native-binary",
        ".dll": "native-binary",
        ".sys": "native-binary",
        ".elf": "native-binary",
        ".so": "native-binary",
        ".dylib": "native-binary",
        ".macho": "native-binary",
        ".pcap": "protocol-pcap",
        ".pcapng": "protocol-pcap",
        ".rs": "protocol-source-implementation",
        ".toml": "protocol-source-implementation",
    }
    if suffix in suffix_map:
        return suffix_map[suffix]

    text = task_text(task)
    for canonical, aliases in ROUTE_ALIASES.items():
        if any(contains_keyword(text, alias) for alias in aliases):
            return canonical
    return ""


def load_capabilities() -> Dict[str, Dict[str, Any]]:
    """Merge the general graph, tool index, and IDA graph without trusting stale state."""
    states: Dict[str, Dict[str, Any]] = {}

    def merge(name: str, state: Dict[str, Any], source: str) -> None:
        current = states.get(name, {})
        merged = dict(current)
        merged.update({key: value for key, value in state.items() if value is not None})
        sources = list(current.get("sources", []))
        if source not in sources:
            sources.append(source)
        merged["sources"] = sources
        states[name] = merged

    if CAPABILITY_GRAPH_PATH.exists():
        graph = read_json(CAPABILITY_GRAPH_PATH)
        for node in as_list(graph.get("nodes")):
            if isinstance(node, dict) and node.get("id"):
                merge(str(node["id"]), node, "capability-graph")

    if TOOL_INDEX_PATH.exists():
        index = read_json(TOOL_INDEX_PATH)
        for tool in as_list(index.get("tools")):
            if isinstance(tool, dict) and tool.get("name"):
                merge(str(tool["name"]), tool, "tool-index")
        for capability in as_list(index.get("capabilities")):
            if isinstance(capability, dict) and capability.get("name"):
                merge(str(capability["name"]), capability, "tool-index")

    if IDA_GRAPH_PATH.exists():
        ida_graph = read_json(IDA_GRAPH_PATH)
        for tool in as_list(ida_graph.get("tools")):
            if isinstance(tool, dict) and tool.get("name"):
                merge(str(tool["name"]), tool, "ida-capability-graph")
        for plugin in as_list(ida_graph.get("plugins")):
            if isinstance(plugin, dict) and plugin.get("name"):
                merge(
                    str(plugin["name"]),
                    {
                        "kind": "ida_plugin",
                        "available": bool(plugin.get("installed", False)),
                        "installed": bool(plugin.get("installed", False)),
                        "load_state": plugin.get("load_state", "unknown"),
                        "modes": plugin.get("modes", []),
                        "role": plugin.get("role", ""),
                        "version": plugin.get("version", ""),
                    },
                    "ida-capability-graph",
                )
        for feature in as_list(ida_graph.get("native_features")):
            if isinstance(feature, dict) and feature.get("name"):
                merge(
                    str(feature["name"]),
                    {
                        "kind": "ida_native_feature",
                        "available": bool(feature.get("available", False)),
                        "installed": bool(feature.get("available", False)),
                        "load_state": feature.get("load_state", "unknown"),
                        "automation": feature.get("automation", ""),
                        "mcp_tools": feature.get("mcp_tools", []),
                        "gates": feature.get("gates", []),
                        "path": feature.get("path", ""),
                    },
                    "ida-capability-graph",
                )
        online_ports = set(int(port) for port in as_list(ida_graph.get("discovery", {}).get("online_mcp_ports")))
        if online_ports:
            merge("idapro", {"service_online": 13337 in online_ports}, "ida-capability-graph")
            merge("idalib-mcp", {"service_online": 13337 in online_ports}, "ida-capability-graph")

    # Generated graphs are optional caches. A command that is available now is
    # stronger evidence than a missing or stale generated entry.
    route_data = read_json(ROUTING_PATH)
    command_names = {"aigx", "git", "git-ida", "hcli", "python", "rg", "sentrux"}
    for route in as_list(route_data.get("macro_routes")):
        if isinstance(route, dict):
            command_names.update(str(name) for name in as_list(route.get("requires_capabilities")))
    for stages in (route_data.get("tool_stages") or {}).values():
        for stage in as_list(stages):
            if isinstance(stage, dict):
                command_names.update(str(name) for name in as_list(stage.get("tools")))

    for name in sorted(command_names):
        path: Optional[str]
        if name == "python":
            path = sys.executable
        elif name == "git-ida":
            git_ida = find_git_ida()
            path = str(git_ida) if git_ida else None
        else:
            path = shutil.which(name)
        if path:
            merge(
                name,
                {
                    "kind": "tool",
                    "available": True,
                    "resolved_path": path,
                    "smoke_status": "discovered",
                },
                "live-command-probe",
            )

    # A local port is stronger evidence than a stale generated cache.
    if probe_tcp(13337):
        merge("idapro", {"service_online": True}, "local-port-probe")
        merge("idalib-mcp", {"service_online": True}, "local-port-probe")
        mcp_tools = probe_mcp_tools(13337)
        if mcp_tools is not None:
            api_ready = bool({"idb_open", "idalib_open"} & mcp_tools)
            merge("idapro", {"api_ready": api_ready, "mcp_tools": sorted(mcp_tools)}, "mcp-tools-probe")
            merge("idalib-mcp", {"api_ready": api_ready, "mcp_tools": sorted(mcp_tools)}, "mcp-tools-probe")

    sentrux = sentrux_cli_state()
    if sentrux.get("status") == "available":
        merge(
            "sentrux",
            {
                "kind": "tool",
                "available": True,
                "resolved_path": sentrux.get("path", ""),
                "version": sentrux.get("version", ""),
                "smoke_status": "pass",
            },
            "local-command-probe",
        )

    return states


def probe_tcp(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def probe_mcp_tools(port: int) -> Optional[set[str]]:
    """Verify the MCP JSON-RPC contract, not just that a TCP port is open."""
    if port in _MCP_TOOL_CACHE:
        return _MCP_TOOL_CACHE[port]
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=1.5) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
        tools = body.get("result", {}).get("tools", [])
        names = {str(item.get("name")) for item in tools if isinstance(item, dict) and item.get("name")}
        _MCP_TOOL_CACHE[port] = names
        return names
    except (OSError, ValueError, urllib.error.URLError):
        _MCP_TOOL_CACHE[port] = None
        return None


def capability_status(name: str, states: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    state = states.get(name)
    if state is None:
        return {"name": name, "status": "missing", "ready": False, "reason": "not_in_capability_graph"}

    available = bool(state.get("available", state.get("tool_available", False)))
    service_online = bool(state.get("service_online", False))
    registered = bool(state.get("mcp_registered", state.get("registered", False)))
    kind = str(state.get("kind", ""))

    if name in {"idapro", "idalib-mcp"}:
        api_ready = state.get("api_ready")
        ready = (service_online or (name == "idapro" and probe_tcp(13337))) and api_ready is not False
    elif name in {"jshookmcp", "anything-analyzer", "burpsuite-mcp"}:
        ready = service_online or (available and registered)
    elif kind == "capability":
        # Capability records also describe local CLIs (Frida, agent-browser,
        # Nmap). Those are ready when their executable is present; only the
        # explicitly named MCP services above require registration.
        ready = service_online or available or bool(state.get("tool_available", False))
    else:
        ready = available

    if ready:
        status = "ready"
        reason = "mcp_api_ready" if name in {"idapro", "idalib-mcp"} else ("service_online" if service_online else "tool_available")
    elif available or registered:
        status = "degraded"
        reason = "registered_or_present_but_not_ready"
    else:
        status = "missing"
        reason = "tool_or_service_unavailable"

    return {
        "name": name,
        "status": status,
        "ready": ready,
        "reason": reason,
        "path": state.get("resolved_path", state.get("path", "")),
        "version": state.get("version", ""),
        "sources": state.get("sources", []),
    }


def tool_action_status(name: str, states: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Describe a planned tool use without promoting an un-smoked plugin to ready."""
    state = states.get(name)
    if state and state.get("kind") in {"ida_plugin", "ida_native_feature"}:
        installed = bool(state.get("installed", state.get("available", False)))
        load_state = str(state.get("load_state", "unknown"))
        native_feature = state.get("kind") == "ida_native_feature"
        if not installed:
            status, ready, reason = "missing", False, "native_feature_unavailable" if native_feature else "plugin_not_installed"
        elif load_state == "built_in":
            status, ready, reason = "ready", True, "builtin_ida_feature"
        elif load_state in {"loaded", "smoke_passed"}:
            status, ready, reason = "ready", True, "plugin_smoke_passed"
        else:
            status, ready, reason = "installed_unverified", False, "native_feature_requires_explicit_smoke" if native_feature else "plugin_requires_ida_smoke"
        return {
            "name": name,
            "status": status,
            "ready": ready,
            "reason": reason,
            "version": state.get("version", ""),
            "modes": state.get("modes", []),
            "role": state.get("role", ""),
            "automation": state.get("automation", ""),
            "gates": state.get("gates", []),
            "sources": state.get("sources", []),
        }
    return capability_status(name, states)


def build_tool_plan(
    route_id: str,
    tool_stages: Dict[str, Any],
    task: Dict[str, Any],
    states: Dict[str, Dict[str, Any]],
    selected_skill: str = "",
) -> Dict[str, Any]:
    """Turn route tool metadata into a checked, phase-ordered execution plan."""
    raw_stages = as_list(tool_stages.get(route_id)) if isinstance(tool_stages, dict) else []
    text = task_text(task)
    teams_task = route_id == "native-binary" and is_ida_teams_task(task)
    requested_mode = normalize(task.get("mode"))
    stages: List[Dict[str, Any]] = []
    for raw_stage in raw_stages:
        if not isinstance(raw_stage, dict):
            continue
        if teams_task and "teams" not in normalize(raw_stage.get("phase", "")):
            continue
        trigger_terms = [str(term) for term in as_list(raw_stage.get("when_any"))]
        matched_terms = [term for term in trigger_terms if contains_keyword(text, term)]
        exclusion_terms = [str(term) for term in as_list(raw_stage.get("unless_any"))]
        excluded_terms = [term for term in exclusion_terms if contains_keyword(text, term)]
        affinity = str(raw_stage.get("skill", ""))
        selected = not affinity or normalize(affinity) in normalize(selected_skill)
        requires_project_path = bool(raw_stage.get("requires_project_path", False))
        project_ready = bool(task.get("project_path"))
        requires_repo_path = bool(raw_stage.get("requires_repo_path", False))
        requires_worktree_contract = bool(raw_stage.get("requires_worktree_contract", False))
        worktree_contract_ready = bool(task.get("teams_worktree_contract_path"))
        # A collaboration contract names its own lab repository and is then
        # checked by teams_collaboration.py. Do not require callers to repeat
        # a private path solely to activate this read-only planning stage.
        repo_ready = bool(
            task.get("repo_path")
            or task.get("teams_contract_path")
            or task.get("teams_worktree_contract_path")
        )
        requires_gui = bool(raw_stage.get("requires_gui", False))
        gui_ready = not requires_gui or requested_mode in {"gui", "interactive", "ui"}
        active = (
            selected
            and (not requires_project_path or project_ready)
            and (not requires_repo_path or repo_ready)
            and (not requires_worktree_contract or worktree_contract_ready)
            and gui_ready
            and not excluded_terms
            and (not trigger_terms or bool(matched_terms))
        )
        tools = [tool_action_status(str(name), states) for name in as_list(raw_stage.get("tools"))]
        api_names = [str(name) for name in as_list(raw_stage.get("mcp_tools"))]
        idapro_state = states.get("idapro", {})
        advertised_api = {str(name) for name in as_list(idapro_state.get("mcp_tools"))}
        api_contract_known = not api_names or bool(advertised_api)
        api_tools = [
            {
                "name": name,
                "status": "ready" if name in advertised_api else ("unverified" if not advertised_api else "missing"),
                "ready": name in advertised_api,
            }
            for name in api_names
        ]
        if not active:
            status = "deferred"
        elif any(tool["status"] == "missing" for tool in tools):
            status = "blocked"
        elif any(item["status"] == "missing" for item in api_tools):
            status = "blocked"
        elif any(tool["status"] == "installed_unverified" for tool in tools):
            status = "needs_smoke"
        elif not api_contract_known:
            status = "degraded"
        elif any(not tool["ready"] for tool in tools):
            status = "degraded"
        else:
            status = "ready"
        stages.append(
            {
                "phase": str(raw_stage.get("phase", "analysis")),
                "purpose": str(raw_stage.get("purpose", "")),
                "execution": str(raw_stage.get("execution", "skill")),
                "active": active,
                "activation": (
                    f"not_selected:{affinity}"
                    if not selected
                    else (
                        "excluded:" + ",".join(excluded_terms)
                        if excluded_terms
                        else (
                            "project_path_required"
                            if requires_project_path and not project_ready
                            else (
                                "teams_context_required"
                                if requires_repo_path and not repo_ready
                                else (
                                    "teams_worktree_contract_required"
                                    if requires_worktree_contract and not worktree_contract_ready
                                    else (
                                        "gui_mode_required"
                                        if requires_gui and not gui_ready
                                        else ("default" if not trigger_terms else ("matched:" + ",".join(matched_terms) if matched_terms else "conditional_not_requested"))
                                    )
                                )
                            )
                        )
                    )
                ),
                "status": status,
                "tools": tools,
                "mcp_tools": api_tools,
                "requires_gui": requires_gui,
                "requires_repo_path": requires_repo_path,
                "requires_worktree_contract": requires_worktree_contract,
                "guidance": str(raw_stage.get("guidance", "")),
            }
        )
    return {"route_id": route_id, "stages": stages}


def route_skill_path(route: Dict[str, Any], fallback: Optional[str] = None) -> str:
    return str(fallback or route.get("primary_skill", ""))


def absolute_skill_path(path_text: str) -> Path:
    path = Path(path_text)
    if path_text.startswith("../"):
        return (SKILLS_ROOT / path).resolve()
    return (SKILLS_ROOT / path).resolve()


def module_name(skill_path: str) -> str:
    parts = Path(skill_path).parts
    for part in parts:
        if part in {"SKILL.md", "references", "scripts"}:
            continue
        if part == "..":
            continue
        return part
    return Path(skill_path).stem


def route_alias_match(route_id: str, text: str) -> List[str]:
    return [alias for alias in ROUTE_ALIASES.get(route_id, ()) if contains_keyword(text, alias)]


def score_route(route: Dict[str, Any], task: Dict[str, Any], target_kind: str) -> Dict[str, Any]:
    route_id = str(route.get("id", ""))
    text = task_text(task)
    score = 0
    signals: List[str] = []
    explicit_route = normalize(task.get("route_id"))

    if explicit_route:
        if explicit_route == route_id:
            score += 10000
            signals.append("explicit_route_id")
        else:
            return {"route": route, "score": -1, "signals": []}

    route_targets = {normalize(item) for item in as_list(route.get("target_kinds"))}
    target_match = target_kind == route_id or target_kind in route_targets
    if target_match:
        score += 100
        signals.append(f"target_kind:{target_kind}")

    aliases = route_alias_match(route_id, text)
    if aliases:
        score += min(60, len(aliases) * 12)
        signals.extend(f"alias:{alias}" for alias in aliases[:5])

    for keyword in as_list(route.get("intent_keywords")):
        if contains_keyword(text, keyword):
            score += 10
            signals.append(f"keyword:{keyword}")

    return {"route": route, "score": score, "signals": signals}


def is_authorized(task: Dict[str, Any]) -> bool:
    scope = task.get("authorization_scope")
    if isinstance(scope, dict):
        kind = normalize(scope.get("kind"))
    else:
        kind = normalize(scope)
    return kind in AUTHORIZED_SCOPE_KINDS


def is_security_task(route_id: str, task: Dict[str, Any]) -> bool:
    text = normalize(task_text(task))
    return route_id in SECURITY_ROUTE_IDS or any(word in text for word in SECURITY_WORDS)


def condition_matches(condition: str, task: Dict[str, Any], primary_missing: Sequence[str]) -> bool:
    value = normalize(condition)
    text = normalize(task_text(task))
    mode = normalize(task.get("mode"))
    evidence = normalize(task.get("evidence"))
    missing = set(primary_missing)

    if value == "idapro_unavailable":
        return (
            "idapro" in missing
            or "idalib-mcp" in missing
            or any(contains_keyword(text, word) for word in ("radare2", "r2", "radiff2"))
        )
    if value == "cli_only_or_ida_missing":
        return (
            mode in {"cli", "cli_only", "headless"}
            or "idapro" in missing
            or any(word in text for word in ("radare2", " r2 ", "radiff2"))
        )
    if value == "ghidra_available_and_ida_missing":
        return "idapro" in missing and "analyzeHeadless" not in missing
    if value == "native_validation_detected":
        return any(word in text or word in evidence for word in ("native", "so", "dll", "sys", "native_validation", "原生"))
    if value == "dynamic_verification_needed":
        return any(word in text for word in ("dynamic", "动态", "hook", "注入", "runtime", "运行时", "verify", "验证"))
    if value == "runtime_observation_needed":
        return any(word in text for word in ("runtime", "运行时", "浏览器采样", "observe", "观察", "capture", "抓取"))
    if value == "hook_or_cdp_needed":
        return any(word in text for word in ("hook", "cdp", "jshookmcp", "断点", "拦截", "注入"))
    if value == "exploit_path_requested":
        return any(word in text for word in ("exploit", "漏洞利用", "pwn", "rop", "利用链", "武器化"))
    if value == "browser_origin_protocol":
        return any(word in text for word in ("browser", "浏览器", "websocket", "http", "frontend", "前端"))
    if value == "ctf_fixture":
        scope = task.get("authorization_scope", {})
        kind = normalize(scope.get("kind") if isinstance(scope, dict) else scope)
        return kind == "ctf" or "ctf" in text
    if value == "runtime_or_live_endpoint_needed":
        return any(word in text for word in ("live", "endpoint", "在线", "实时", "运行时"))
    if value == "compiled_binary_needed":
        return any(word in text for word in ("binary", "二进制", "compile", "编译", "exe", "dll", "elf"))
    if value == "websocket_or_http_origin":
        return any(word in text for word in ("websocket", "http", "api", "接口"))
    if value == "llm_agent_surface":
        return any(word in text for word in ("llm", "agent", "prompt", "模型", "智能体"))
    if value == "api_specific":
        return any(word in text for word in ("api", "graphql", "jwt", "oauth", "接口"))
    if value == "end_to_end_attack_chain":
        return any(word in text for word in ("end-to-end", "full chain", "完整攻击链", "从外网", "域控"))
    if value == "evolution_loop_needed":
        return any(word in text for word in ("evolve", "自进化", "经验回流", "promotion", "晋级"))
    return False


def fallback_requirements(skill_path: str) -> Tuple[str, ...]:
    module = module_name(skill_path)
    return FALLBACK_CAPABILITIES.get(module, ())


def choose_fallback(route: Dict[str, Any], task: Dict[str, Any], missing: Sequence[str], states: Dict[str, Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    attempts: List[Dict[str, Any]] = []
    for edge in as_list(route.get("fallback_edges")):
        if not isinstance(edge, dict):
            continue
        condition = str(edge.get("when", ""))
        goto = str(edge.get("goto", ""))
        if not condition_matches(condition, task, missing):
            continue
        required = list(
            dict.fromkeys(
                [
                    *fallback_requirements(goto),
                    *[str(item) for item in as_list(edge.get("requires_capabilities"))],
                ]
            )
        )
        checks = [capability_status(name, states) for name in required]
        missing_fallback = [item["name"] for item in checks if not item["ready"]]
        attempt = {
            "when": condition,
            "skill": goto,
            "required_capabilities": required,
            "missing_capabilities": missing_fallback,
            "ready": not missing_fallback,
        }
        attempts.append(attempt)
        if not missing_fallback:
            return attempt, attempts
    return None, attempts


def dynamic_requirements(route_id: str, task: Dict[str, Any]) -> List[str]:
    """Add requirements that depend on the requested execution mode."""
    text = normalize(task_text(task))
    requirements: List[str] = []
    if route_id == "protocol-source-implementation":
        if any(word in text for word in ("rust", "cargo", ".rs")):
            requirements.extend(("cargo", "rustc"))
        if any(word in text for word in ("go workspace", "golang", " go ")):
            requirements.append("go")
        if any(has_explicit_token(text, word) for word in ("protobuf", "protoc", "proto3")):
            requirements.append("protoc")
    elif route_id == "protocol-pcap":
        if any(word in text for word in ("tshark", "wireshark", "抓包解析")):
            requirements.append("tshark")
    elif route_id == "js-browser-signature":
        if any(word in text for word in ("jshookmcp", "hook", "cdp", "断点", "拦截")):
            requirements.append("jshookmcp")
    elif route_id == "mobile-reverse":
        if any(word in text for word in ("android", "安卓", "apk", "smali")):
            requirements.extend(("jadx", "apktool", "adb"))
    elif route_id == "firmware-pentest":
        if any(word in text for word in ("extract", "提取", "binwalk")):
            requirements.append("binwalk")
        if any(word in text for word in ("qemu", "仿真", "emulation")):
            requirements.append("qemu-system-arm")
        if any(word in text for word in ("fuzz", "模糊测试", "afl++")):
            requirements.append("afl-fuzz")
    elif route_id == "api-security":
        if any(word in text for word in ("nuclei", "漏洞扫描")):
            requirements.append("nuclei")
        if any(word in text for word in ("burp", "burpsuite")):
            requirements.append("burpsuite-mcp")
    elif route_id == "supply-chain-security":
        if any(word in text for word in ("trivy", "容器扫描")):
            requirements.append("trivy")
        if any(word in text for word in ("syft", "sbom")):
            requirements.append("syft")
        if any(word in text for word in ("gitleaks", "secret scan", "密钥扫描")):
            requirements.append("gitleaks")
    elif route_id == "pwn-chain":
        if "pwntools" in text:
            requirements.append("pwntools")
    return list(dict.fromkeys(requirements))


def explicit_toolchain_requested(route: Dict[str, Any], task: Dict[str, Any]) -> bool:
    route_id = str(route.get("id", ""))
    text = normalize(task_text(task))
    if route_id == "native-binary":
        return any(contains_keyword(text, word) for word in ("radare2", "r2", "radiff2"))
    if route_id == "js-browser-signature":
        return any(word in text for word in ("jshookmcp", "cdp", "hook"))
    return False


def build_entrypoint(
    skill_path: str,
    task: Dict[str, Any],
    project_intelligence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    module = module_name(skill_path)
    input_path = str(task.get("input_path") or "")
    script: Optional[Path] = None
    command: Optional[List[str]] = None
    reason = "skill_requires_workflow_execution"

    if module == "apk-reverse":
        # The legacy decoder is PowerShell-only. Keep the route descriptive
        # until a Python implementation exists instead of invoking a second
        # shell contract from the standard CLI.
        reason = "python_entrypoint_not_available"
    elif module == "ida-reverse":
        if is_ida_teams_task(task):
            repo_path = str(task.get("repo_path") or "")
            contract_path = str(task.get("teams_contract_path") or "")
            worktree_contract_path = str(task.get("teams_worktree_contract_path") or "")
            if is_teams_worktree_task(task):
                reason = "controlled_teams_worktree_lab"
                if worktree_contract_path:
                    command = [sys.executable, "-m", "reverse_skill", "teams", "lab", worktree_contract_path]
                    if task.get("teams_lab_apply"):
                        command.append("--apply")
            elif contract_path:
                command = [sys.executable, "-m", "reverse_skill", "teams", "plan", contract_path]
                reason = "controlled_teams_collaboration_plan"
            elif repo_path:
                command = [sys.executable, "-m", "reverse_skill", "teams", "preflight", repo_path]
                reason = "controlled_git_ida_preflight"
        else:
            if input_path:
                command = [sys.executable, "-m", "reverse_skill", "open", input_path]
                reason = "controlled_idalib_open_entrypoint"
    elif module == "reverse-engineering" and is_workspace_search_task(task):
        search_path = str(task.get("search_path") or "")
        search_query = str(task.get("search_query") or "")
        if search_path and search_query:
            command = [sys.executable, "-m", "reverse_skill", "search", search_path, search_query]
            search_engine = str(task.get("search_engine") or "auto")
            command.extend(["--engine", search_engine])
            for glob in as_list(task.get("search_globs")):
                if isinstance(glob, str) and glob:
                    command.extend(["--glob", glob])
            reason = "controlled_workspace_search"
    elif module == "radare2":
        reason = "python_entrypoint_not_available"
    elif module == "evolution" and has_explicit_token(task_text(task), "sentrux"):
        sentrux = (project_intelligence or {}).get("sentrux", {})
        scoped_command = (sentrux.get("commands") or {}).get("check")
        if isinstance(scoped_command, list) and scoped_command:
            command = [str(item) for item in scoped_command]
            reason = "controlled_code_intel_sentrux_check"

    result: Dict[str, Any] = {
        "mode": "script" if script else ("cli" if command else "skill"),
        "skill_file": str(absolute_skill_path(skill_path)),
        "script": str(script.resolve()) if script else None,
        "command": command,
        "executable": bool(command and (not script or script.exists())),
        "reason": reason,
    }
    if module == "ida-reverse" and is_ida_teams_task(task):
        if is_teams_worktree_task(task) and not task.get("teams_worktree_contract_path"):
            result["requires"] = ["teams_worktree_contract"]
        elif not (task.get("repo_path") or task.get("teams_contract_path") or task.get("teams_worktree_contract_path")):
            result["requires"] = ["teams_context"]
    elif module == "reverse-engineering" and is_workspace_search_task(task):
        required = []
        if not task.get("search_path"):
            required.append("search_path")
        if not task.get("search_query"):
            required.append("search_query")
        if required:
            result["requires"] = required
    elif module == "evolution" and has_explicit_token(task_text(task), "sentrux") and not command:
        result["requires"] = ["sentrux_scope"]
    elif not input_path and module in {"apk-reverse", "ida-reverse", "radare2"}:
        result["requires"] = ["input_path"]
    return result


def build_plan(task: Dict[str, Any]) -> Dict[str, Any]:
    routes_data = read_json(ROUTING_PATH)
    routes = [item for item in as_list(routes_data.get("macro_routes")) if isinstance(item, dict)]
    tool_stages = routes_data.get("tool_stages", {})
    project_intelligence = (
        collect_project_intelligence(
            str(task["project_path"]),
            [str(item) for item in as_list(task.get("aigx_targets"))],
            str(task.get("aigx_command")) if task.get("aigx_command") else None,
        )
        if task.get("project_path")
        else None
    )
    if not routes:
        raise ValueError("routing.json has no macro_routes")

    target_kind = infer_target_kind(task)
    scored = [score_route(route, task, target_kind) for route in routes]
    scored = [item for item in scored if item["score"] >= 0]
    scored.sort(key=lambda item: item["score"], reverse=True)
    if not scored or scored[0]["score"] <= 0:
        return {
            "schema_version": 1,
            "status": "no_route",
            "target_kind": target_kind,
            "task": task,
            "reason": "no_target_or_intent_match",
            "candidate_routes": [item["route"].get("id") for item in scored[:3]],
        }

    selected = scored[0]
    route = selected["route"]
    states = load_capabilities()
    teams_git_task = str(route.get("id", "")) == "native-binary" and is_ida_teams_task(task)
    teams_worktree_task = teams_git_task and is_teams_worktree_task(task)
    teams_artifact_analysis_task = teams_git_task and is_teams_artifact_analysis_task(task)
    workspace_search_task = str(route.get("id", "")) == "workspace-search"
    required = (
        ["git"]
        if teams_worktree_task
        else (["git-ida"] if teams_git_task else [str(item) for item in as_list(route.get("requires_capabilities"))])
    )
    required.extend(dynamic_requirements(str(route.get("id", "")), task))
    required = list(dict.fromkeys(required))
    checks = [capability_status(name, states) for name in required]
    missing = [item["name"] for item in checks if not item["ready"]]

    selected_skill = str(route.get("primary_skill", ""))
    selected_route_id = str(route.get("id", ""))
    selected_service: Optional[str] = None
    fallback: Optional[Dict[str, Any]] = None
    fallback_attempts: List[Dict[str, Any]] = []
    status = "ready"
    block_reasons: List[str] = []
    input_path = str(task.get("input_path") or "")
    input_check: Dict[str, Any] = {"path": input_path, "status": "not_provided", "ready": True}
    if input_path:
        input_candidate = Path(input_path).expanduser()
        input_is_file = input_candidate.is_file()
        input_exists = input_candidate.exists()
        input_check = {
            "path": str(input_candidate),
            "status": "ready" if input_is_file else ("invalid" if input_exists else "missing"),
            "ready": input_is_file,
            "reason": "path_is_file" if input_is_file else ("input_path_not_file" if input_exists else "input_path_not_found"),
        }
        if not input_is_file:
            status = "blocked"
            block_reasons.append("input_path_not_file" if input_exists else "input_path_missing")

    search_path = str(task.get("search_path") or "")
    search_query = str(task.get("search_query") or "")
    search_check: Dict[str, Any] = {
        "path": search_path,
        "query_provided": bool(search_query),
        "status": "not_applicable" if not workspace_search_task else "not_provided",
        "ready": not workspace_search_task,
    }
    if workspace_search_task:
        if not search_path:
            status = "blocked"
            block_reasons.append("search_path_required")
        elif not Path(search_path).expanduser().is_dir():
            search_check.update({"status": "missing", "ready": False, "reason": "search_path_not_found"})
            status = "blocked"
            block_reasons.append("search_path_missing")
        elif not search_query:
            search_check.update({"status": "query_required", "ready": False, "reason": "search_query_required"})
            status = "blocked"
            block_reasons.append("search_query_required")
        else:
            search_check.update({"status": "ready", "ready": True, "reason": "search_path_and_query_provided"})

    project_path = str(task.get("project_path") or "")
    project_required = str(route.get("id", "")) == "architecture-governance"
    project_check: Dict[str, Any] = {"path": project_path, "status": "not_provided", "ready": not project_required}
    if project_path:
        project_candidate = Path(project_path).expanduser()
        project_check = {
            "path": str(project_candidate),
            "status": "ready" if project_candidate.is_dir() else "missing",
            "ready": project_candidate.is_dir(),
            "reason": "project_directory_exists" if project_candidate.is_dir() else "project_path_not_found",
        }
    if project_required and not project_check["ready"]:
        status = "blocked"
        block_reasons.append("project_path_required")

    aigx_ready = True
    aigx_observation: Dict[str, Any] = {}
    if project_path:
        aigx_observation = (project_intelligence or {}).get("aigx", {})
        aigx_ready = bool(aigx_observation.get("ready"))
        if not aigx_ready:
            status = "blocked"
            reason = str(aigx_observation.get("reason") or "aigx_context_blocked")
            block_reasons.append(reason)
            for item in as_list(aigx_observation.get("reasons")):
                block_reasons.append(str(item).split(":", 1)[0])

    contract_path = str(task.get("teams_contract_path") or "")
    contract_check: Dict[str, Any] = {"path": contract_path, "status": "not_provided", "ready": True}
    if contract_path:
        contract_candidate = Path(contract_path).expanduser()
        contract_check = {
            "path": str(contract_candidate),
            "status": "ready" if contract_candidate.is_file() else "missing",
            "ready": contract_candidate.is_file(),
            "reason": "contract_file_exists" if contract_candidate.is_file() else "teams_contract_path_not_found",
        }
        if not contract_check["ready"]:
            status = "blocked"
            block_reasons.append("teams_contract_path_missing")

    worktree_contract_path = str(task.get("teams_worktree_contract_path") or "")
    worktree_contract_check: Dict[str, Any] = {
        "path": worktree_contract_path,
        "status": "not_provided",
        "ready": not teams_worktree_task,
    }
    if worktree_contract_path:
        worktree_contract_candidate = Path(worktree_contract_path).expanduser()
        worktree_contract_check = {
            "path": str(worktree_contract_candidate),
            "status": "ready" if worktree_contract_candidate.is_file() else "missing",
            "ready": worktree_contract_candidate.is_file(),
            "reason": "contract_file_exists" if worktree_contract_candidate.is_file() else "teams_worktree_contract_path_not_found",
        }
        if not worktree_contract_check["ready"]:
            status = "blocked"
            block_reasons.append("teams_worktree_contract_path_missing")
    elif teams_worktree_task:
        status = "blocked"
        block_reasons.append("teams_worktree_contract_required")

    repo_path = str(task.get("repo_path") or "")
    repo_required = teams_git_task and not teams_worktree_task and not contract_path and not worktree_contract_path
    repo_check: Dict[str, Any] = {"path": repo_path, "status": "not_provided", "ready": not repo_required}
    if repo_path:
        repo_candidate = Path(repo_path).expanduser()
        repo_check = {
            "path": str(repo_candidate),
            "status": "ready" if repo_candidate.is_dir() else "missing",
            "ready": repo_candidate.is_dir(),
            "reason": "repository_directory_exists" if repo_candidate.is_dir() else "repo_path_not_found",
        }
    if repo_required and not repo_check["ready"]:
        status = "blocked"
        block_reasons.append("repo_path_required")

    sentrux_rules_ready = True
    sentrux_gate_ready = True
    sentrux_observation: Dict[str, Any] = {}
    if project_required and project_intelligence:
        sentrux_observation = project_intelligence.get("sentrux", {})
        sentrux_scope = sentrux_observation.get("scope", {})
        if not sentrux_scope.get("ready"):
            sentrux_gate_ready = False
            status = "blocked"
            block_reasons.append(str(sentrux_scope.get("reason") or "sentrux_scope_unresolved"))
        elif not sentrux_observation.get("ready"):
            sentrux_gate_ready = False
            status = "blocked"
            block_reasons.append("sentrux_gate_failed")
        if sentrux_observation.get("rules") == "missing":
            sentrux_rules_ready = False
            status = "blocked"
            block_reasons.append("sentrux_rules_missing")

    forced_toolchain = explicit_toolchain_requested(route, task)
    if missing or forced_toolchain:
        fallback, fallback_attempts = choose_fallback(route, task, missing, states)
        if fallback:
            fallback_target = str(fallback["skill"])
            if fallback_target.endswith(".md"):
                selected_skill = fallback_target
            else:
                selected_service = fallback_target
            selected_route_id = f"{selected_route_id}:fallback"
            required = list(fallback["required_capabilities"])
            checks = [capability_status(name, states) for name in required]
            missing = [item["name"] for item in checks if not item["ready"]]
        elif forced_toolchain:
            requested = fallback_attempts[0] if fallback_attempts else None
            if requested:
                requested_target = str(requested["skill"])
                if requested_target.endswith(".md"):
                    selected_skill = requested_target
                else:
                    selected_service = requested_target
                selected_route_id = f"{selected_route_id}:fallback"
                required = list(requested.get("required_capabilities", []))
                checks = [capability_status(name, states) for name in required]
            attempted_missing = [
                name
                for attempt in fallback_attempts
                for name in attempt.get("missing_capabilities", [])
            ]
            missing = list(dict.fromkeys(attempted_missing))
            status = "blocked"
            block_reasons.append("requested_toolchain_unavailable")
        if missing:
            status = "blocked"
            block_reasons.append("required_capability_missing")

    security_gate = is_security_task(str(route.get("id", "")), task)
    if security_gate and not is_authorized(task):
        status = "blocked"
        block_reasons.append("authorization_scope_required")

    entrypoint = build_entrypoint(selected_skill, task, project_intelligence)
    if teams_artifact_analysis_task:
        status = "blocked"
        block_reasons.append("composite_workflow_not_supported")
        entrypoint.update(
            {
                "command": None,
                "executable": False,
                "reason": "composite_workflow_not_supported",
                "requires": ["separate_teams_and_artifact_analysis_stages"],
            }
        )
    if selected_route_id.startswith("native-binary") and not teams_git_task and not input_path:
        requirements = [str(item) for item in as_list(entrypoint.get("requires"))]
        if "input_path" not in requirements:
            entrypoint["requires"] = [*requirements, "input_path"]
    if "input_path" in as_list(entrypoint.get("requires")):
        input_check.update(
            {
                "status": "required",
                "ready": False,
                "reason": "input_path_required",
            }
        )
        status = "blocked"
        block_reasons.append("input_path_required")
    tool_plan = build_tool_plan(str(route.get("id", "")), tool_stages, task, states, selected_skill)
    if entrypoint.get("script") and not Path(str(entrypoint["script"])).exists():
        status = "blocked"
        block_reasons.append("entrypoint_missing")

    success_oracles = (
        as_list(route.get("success_oracles"))
        if teams_artifact_analysis_task
        else (
        ["source_dirty_changes_excluded", "isolated_lab_plan_recorded", "isolated_worktrees_created_if_apply_requested"]
        if teams_worktree_task
        else (
            ["collaboration_roles_validated", "source_project_separation_recorded"]
            if teams_git_task and contract_path
            else (["git_ida_readiness_recorded", "source_repository_unchanged"] if teams_git_task else as_list(route.get("success_oracles")))
        )
        )
    )
    if project_path:
        success_oracles = ["aigx_lint_passed", *success_oracles]
        if as_list(task.get("aigx_targets")):
            success_oracles.insert(1, "aigx_edit_boundaries_resolved")

    plan = {
        "schema_version": 1,
        "status": status,
        "target_kind": target_kind,
        "task": task,
        "route": {
            "id": selected_route_id,
            "base_id": route.get("id"),
            "skill": selected_skill,
            "skill_file": str(absolute_skill_path(selected_skill)),
            "score": selected["score"],
            "signals": selected["signals"],
            "selected_by": "explicit_route_id" if task.get("route_id") else "deterministic_target_intent_score",
        },
        "preflight": {
            "required_capabilities": required,
            "checks": checks,
            "input": input_check,
            "search": search_check,
            "project": project_check,
            "repository": repo_check,
            "teams_contract": contract_check,
            "teams_worktree_contract": worktree_contract_check,
            "composite_workflow": {
                "status": "blocked" if teams_artifact_analysis_task else "not_applicable",
                "ready": not teams_artifact_analysis_task,
                "reason": "composite_workflow_not_supported" if teams_artifact_analysis_task else None,
            },
            "aigx": {
                "status": aigx_observation.get("status", "not_applicable"),
                "ready": aigx_ready,
                "reason": aigx_observation.get("reason"),
                "boundaries": aigx_observation.get("boundaries", []),
            },
            "sentrux": {
                "rules": sentrux_observation.get("rules", "not_applicable"),
                "baseline": sentrux_observation.get("baseline", "not_applicable"),
                "rules_ready": sentrux_rules_ready,
                "gate_ready": sentrux_gate_ready,
                "scope": sentrux_observation.get("scope", {}),
            },
            "missing_capabilities": missing,
            "status": "pass" if not missing and input_check["ready"] and search_check["ready"] and project_check["ready"] and repo_check["ready"] and contract_check["ready"] and worktree_contract_check["ready"] and not teams_artifact_analysis_task and aigx_ready and sentrux_rules_ready and sentrux_gate_ready else "blocked",
            "sources": sorted({source for check in checks for source in check.get("sources", [])}),
        },
        "authorization": {
            "required": security_gate,
            "passed": is_authorized(task) if security_gate else True,
        },
        "project_intelligence": project_intelligence,
        "fallback": {
            "selected": fallback,
            "attempts": fallback_attempts,
        },
        "tool_plan": tool_plan,
        "dispatch": entrypoint,
        "success_oracles": success_oracles,
        "next_actions": [],
    }
    if selected_service:
        plan["dispatch"]["service"] = selected_service

    if status == "ready":
        plan["next_actions"] = [
            "resolve the AIGX boundary before adding any edit target",
            f"read {entrypoint['skill_file']}",
            "execute the skill's first workflow step",
            "follow active tool_plan stages in phase order",
            "record evidence against the success_oracles",
        ]
        if project_intelligence and project_intelligence.get("code_intel", {}).get("status") != "authoritative":
            plan["next_actions"].append("treat project structure as observational until a current Code Intel run is published")
        if project_intelligence and project_intelligence.get("sentrux", {}).get("baseline") == "missing":
            plan["next_actions"].append("do not claim structural regression protection until the project owner establishes a Sentrux baseline")
    else:
        plan["next_actions"] = [
            f"resolve capability: {name}" for name in missing
        ]
        if any(reason in block_reasons for reason in ("input_path_missing", "input_path_not_file", "input_path_required")):
            plan["next_actions"].append("provide an existing input_path before execution")
        if "search_path_required" in block_reasons:
            plan["next_actions"].append("provide a search_path before controlled workspace search")
        if "search_path_missing" in block_reasons:
            plan["next_actions"].append("provide an existing search_path before controlled workspace search")
        if "search_query_required" in block_reasons:
            plan["next_actions"].append("provide a search_query before controlled workspace search")
        if "project_path_required" in block_reasons:
            plan["next_actions"].append("provide an existing project_path before Sentrux execution")
        if "aigx_genome_missing" in block_reasons:
            plan["next_actions"].append("add a conforming project-owned .aigx genome before project routing")
        if "aigx_cli_unavailable" in block_reasons:
            plan["next_actions"].append("install the official aigx validator before project routing")
        if "aigx_lint_failed" in block_reasons:
            plan["next_actions"].append("fix the project genome until official aigx lint passes")
        if "aigx_boundary_missing" in block_reasons:
            plan["next_actions"].append("add the edit target to .aigx/files.aigx with binding checks")
        if "aigx_target_outside_project" in block_reasons:
            plan["next_actions"].append("keep every AIGX edit target inside project_path")
        if "aigx_target_not_found" in block_reasons:
            plan["next_actions"].append("provide an existing project file as the AIGX edit target")
        if "repo_path_required" in block_reasons:
            plan["next_actions"].append("provide an existing repo_path before IDA Teams Git preflight")
        if "teams_contract_path_missing" in block_reasons:
            plan["next_actions"].append("provide an existing teams_contract_path before collaboration planning")
        if "teams_worktree_contract_path_missing" in block_reasons:
            plan["next_actions"].append("provide an existing teams_worktree_contract_path before isolated lab creation")
        if "teams_worktree_contract_required" in block_reasons:
            plan["next_actions"].append("provide a private teams_worktree_contract_path before isolated lab creation")
        if "sentrux_rules_missing" in block_reasons:
            plan["next_actions"].append("add project-owned .sentrux/rules.toml before treating Sentrux as an architecture gate")
        if any(reason.startswith("sentrux_scope_") for reason in block_reasons):
            plan["next_actions"].append("resolve one AIGX-owned architecture-governance Sentrux scope before execution")
        if "sentrux_gate_failed" in block_reasons:
            plan["next_actions"].append("fix the scoped Code Intel Sentrux gate before execution")
        if "authorization_scope_required" in block_reasons:
            plan["next_actions"].append("provide an authorized scope before any security action")
        if "composite_workflow_not_supported" in block_reasons:
            plan["next_actions"].append(
                "run the IDA Teams preflight or lab plan first, then start a separate artifact-analysis route with the input_path"
            )
        plan["next_actions"].append("do not execute the route while blocked")

    if block_reasons:
        plan["block_reasons"] = block_reasons
    return plan


def parse_task(args: argparse.Namespace) -> Dict[str, Any]:
    if args.task_file:
        task = read_json(Path(args.task_file))
    elif args.json:
        value = json.loads(args.json)
        if not isinstance(value, dict):
            raise ValueError("--json must contain an object")
        task = value
    else:
        task = {}

    if args.task:
        task["task"] = args.task
    if args.input_path:
        task["input_path"] = args.input_path
    if args.target_kind:
        task["target_kind"] = args.target_kind
    if args.mode:
        task["mode"] = args.mode
    if args.route_id:
        task["route_id"] = args.route_id
    if args.authorization_scope:
        task["authorization_scope"] = {"kind": args.authorization_scope}
    if args.project_path:
        task["project_path"] = args.project_path
    if args.aigx_target:
        task["aigx_targets"] = args.aigx_target
    if args.aigx_command:
        task["aigx_command"] = args.aigx_command
    if args.search_path:
        task["search_path"] = args.search_path
    if args.search_query:
        task["search_query"] = args.search_query
    if args.search_engine:
        task["search_engine"] = args.search_engine
    if args.search_glob:
        task["search_globs"] = args.search_glob
    if (args.search_path or args.search_query) and not task.get("target_kind"):
        task["target_kind"] = "workspace-search"
    if args.repo_path:
        task["repo_path"] = args.repo_path
    if args.teams_contract:
        task["teams_contract_path"] = args.teams_contract
    if args.teams_worktree_contract:
        task["teams_worktree_contract_path"] = args.teams_worktree_contract
    if args.apply_teams_lab:
        task["teams_lab_apply"] = True
    if not task.get("task") and not task.get("intent") and not task.get("target_kind") and not task.get("input_path") and not task.get("search_query"):
        raise ValueError("provide --task, --json, --task-file, --target-kind, or --input-path")
    return task


def execute_plan(plan: Dict[str, Any]) -> int:
    if plan.get("status") != "ready":
        return EXIT_BLOCKED
    dispatch = plan.get("dispatch", {})
    command = dispatch.get("command")
    if not command or not dispatch.get("executable"):
        plan["execution"] = {"status": "no_entrypoint", "reason": dispatch.get("reason")}
        return EXIT_NO_ENTRYPOINT

    # Keep stdout machine-readable: entrypoint output is returned inside the
    # execution object instead of being interleaved with the router JSON.
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    plan["execution"] = {
        "status": "passed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "command": command,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
    }
    return EXIT_READY if completed.returncode == 0 else EXIT_EXECUTION_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route a reverse/security task to a checked skill dispatch plan")
    parser.add_argument("--task", help="natural-language task description")
    parser.add_argument("--task-file", help="JSON task contract")
    parser.add_argument("--json", help="inline JSON task contract")
    parser.add_argument("--input-path", help="target artifact path")
    parser.add_argument("--target-kind", help="explicit target kind, e.g. pe/apk/pcap")
    parser.add_argument("--mode", help="gui, headless, cli_only, or dynamic")
    parser.add_argument("--route-id", help="explicit route id; use only for a deliberate override")
    parser.add_argument("--authorization-scope", help="ctf, own_asset, lab_fixture, bug_bounty, or engagement")
    parser.add_argument("--project-path", help="target project; a valid root .aigx genome is mandatory")
    parser.add_argument("--aigx-target", action="append", help="project file whose AIGX boundary must resolve; repeatable")
    parser.add_argument("--aigx-command", help="explicit official aigx/aigx-lint executable")
    parser.add_argument("--search-path", help="workspace directory for controlled read-only search")
    parser.add_argument("--search-query", help="ripgrep-compatible search pattern")
    parser.add_argument("--search-engine", choices=("auto", "xcmd", "rg"), help="prefer xcmd only when explicitly requested; auto records fallback")
    parser.add_argument("--search-glob", action="append", help="optional ripgrep glob; may be repeated")
    parser.add_argument("--repo-path", help="target Git repository for the read-only IDA Teams Git-backend preflight")
    parser.add_argument("--teams-contract", help="external JSON contract for the read-only IDA Teams collaboration planner")
    parser.add_argument("--teams-worktree-contract", help="external JSON contract for an isolated IDA Teams worktree lab")
    parser.add_argument("--apply-teams-lab", action="store_true", help="allow --execute to create the named isolated Teams lab")
    parser.add_argument("--execute", action="store_true", help="run an existing controlled entrypoint after checks")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        task = parse_task(args)
        plan = build_plan(task)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"schema_version": 1, "status": "invalid", "error": str(error)}, ensure_ascii=False, indent=2 if args.pretty else None))
        return EXIT_INVALID

    if args.execute:
        exit_code = execute_plan(plan)
    else:
        exit_code = {
            "ready": EXIT_READY,
            "blocked": EXIT_BLOCKED,
            "no_route": EXIT_NO_ROUTE,
        }.get(str(plan.get("status")), EXIT_INVALID)

    print(json.dumps(plan, ensure_ascii=False, indent=2 if args.pretty else None))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
