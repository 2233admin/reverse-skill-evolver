"""Python quality gates for the reverse-skill package and repository.

Each gate returns a stable result dict; the CLI turns failures into the
documented exit code 5 (controlled operation failed). No PowerShell/PSParser
gate is added or required.

Gates:
- leak-scan:        field-journal / promotion-candidate sensitive-info scan
- doc-facts:        README/OpenCLI/CLI surface and packaged-data drift check
- version:          pyproject / package / OpenCLI / CHANGELOG consistency
- routing-coherence: routing.json integrity + referenced skill path existence
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent


def _resolve_repo_root() -> Path:
    """Resolve the repository root for repo-bound gates.

    Prefer the current working directory when it looks like a repo checkout
    (pyproject.toml + skills/), so the gates work both from the source tree and
    from an installed wheel run inside a repo. Falls back to the package parent.
    """
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").is_file() and (cwd / "skills").is_dir():
        return cwd
    return REPO_ROOT

# --- Leak scan --------------------------------------------------------------

ALLOWED_EMAIL_DOMAINS = (
    "example.com",
    "example.org",
    "example.net",
    "example.edu",
    "example.test",
    "test",
    "localhost",
    "local",
    "invalid",
)

LEAK_PATTERNS: List[Dict[str, Any]] = [
    {
        "name": "Public IPv4",
        "regex": re.compile(
            r"\b(?!(?:10\.|127\.|172\.(?:1[6-9]|2[0-9]|3[01])\.|192\.168\.|169\.254\.|100\.100\.|198\.51\.100\.|203\.0\.113\.|192\.0\.2\.|0\.0\.0\.|224\.|25[0-5]\.))(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
        ),
    },
    {"name": "Email", "regex": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")},
    {"name": "CN mobile", "regex": re.compile(r"\b1[3-9][0-9]{9}\b")},
    {"name": "JWT", "regex": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")},
    {"name": "AWS Access Key", "regex": re.compile(r"\bAKIA[0-9A-Z]{16}\b")},
    {"name": "OpenAI key", "regex": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b")},
    {"name": "GitHub token", "regex": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")},
    {"name": "npm token", "regex": re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b")},
    {"name": "Slack token", "regex": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")},
    {"name": "Google API key", "regex": re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b")},
    {"name": "Stripe live key", "regex": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b")},
]

SCAN_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml", ".py"}


def _email_allowed(value: str) -> bool:
    domain = value.rsplit("@", 1)[-1].lower()
    return any(domain == allowed or domain.endswith("." + allowed) for allowed in ALLOWED_EMAIL_DOMAINS)


def leak_scan(path: str, report_only: bool = False) -> Dict[str, Any]:
    """Scan a file or directory tree for un-anonymized sensitive information."""
    target = Path(path).expanduser()
    if target.is_dir():
        files = sorted(p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in SCAN_EXTENSIONS)
    elif target.is_file():
        files = [target]
    else:
        return {"status": "invalid", "reason": "path_not_found", "path": str(target)}

    findings: List[Dict[str, Any]] = []
    for file in files:
        try:
            lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            findings.append({"file": str(file), "line": 0, "kind": "read_error", "value": str(exc)})
            continue
        for index, line in enumerate(lines, 1):
            for pattern in LEAK_PATTERNS:
                for match in pattern["regex"].finditer(line):
                    if pattern["name"] == "Email" and _email_allowed(match.group(0)):
                        continue
                    findings.append(
                        {"file": str(file), "line": index, "kind": pattern["name"], "value": match.group(0)}
                    )

    return {
        "status": "clean" if not findings else ("reported" if report_only else "findings"),
        "path": str(target),
        "scanned_files": len(files),
        "findings": findings,
        "report_only": report_only,
    }


# --- Version consistency ----------------------------------------------------


def _normalize_pep440_style(value: str) -> str:
    return value.strip().lower().replace("-beta.", "b").replace("-alpha.", "a").replace("-rc", "rc")


def version_consistency(repo_root: Path | None = None) -> Dict[str, Any]:
    repo_root = repo_root or _resolve_repo_root()
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    init_py = (repo_root / "reverse_skill" / "__init__.py").read_text(encoding="utf-8")
    opencli = json.loads((repo_root / "reverse-skill.opencli.json").read_text(encoding="utf-8"))

    pyproject_version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    init_version = re.search(r'__version__\s*=\s*"([^"]+)"', init_py)
    opencli_version = opencli.get("info", {}).get("version", "")

    values = {
        "pyproject": pyproject_version.group(1) if pyproject_version else "",
        "package": init_version.group(1) if init_version else "",
        "opencli": opencli_version,
    }
    normalized = {key: _normalize_pep440_style(value) for key, value in values.items()}
    consistent = len(set(normalized.values())) == 1 and bool(normalized["pyproject"])

    changelog_path = repo_root / "CHANGELOG.md"
    changelog_ok = changelog_path.is_file()
    if changelog_ok:
        changelog = changelog_path.read_text(encoding="utf-8")
        current = normalized["pyproject"]
        changelog_ok = ("## [Unreleased]" in changelog) or (f"## [{current}]" in changelog) or (f"## [{values['pyproject']}]" in changelog)

    checks = [
        {"name": "pyproject", "ok": bool(values["pyproject"]), "detail": values["pyproject"]},
        {"name": "package", "ok": values["package"] == values["pyproject"], "detail": values["package"]},
        {"name": "opencli", "ok": values["opencli"] and normalized["opencli"] == normalized["pyproject"], "detail": values["opencli"]},
        {"name": "changelog", "ok": changelog_ok, "detail": "CHANGELOG.md missing or has no current-version section" if not changelog_ok else "present"},
    ]
    failed = [check for check in checks if not check["ok"]]
    return {
        "status": "clean" if not failed else "findings",
        "version": values,
        "checks": checks,
        "failures": failed,
    }


# --- CLI surface drift ------------------------------------------------------


def _top_level_command_names(cli_source: str) -> List[str]:
    """Extract the top-level command/group names from cli.py.

    The authoritative list is the COMMAND_NAMES constant (all click commands and
    groups; group names like case/gates/plugins/teams are included there too).
    """
    match = re.search(r"COMMAND_NAMES\s*=\s*\{(.*?)\}", cli_source, re.DOTALL)
    if not match:
        return []
    names = re.findall(r'"([A-Za-z0-9_-]+)"', match.group(1))
    return sorted(set(names))


def doc_facts(repo_root: Path | None = None) -> Dict[str, Any]:
    repo_root = repo_root or _resolve_repo_root()
    opencli = json.loads((repo_root / "reverse-skill.opencli.json").read_text(encoding="utf-8"))
    cli_source = (repo_root / "reverse_skill" / "cli.py").read_text(encoding="utf-8")

    cli_commands = _top_level_command_names(cli_source)
    opencli_commands = sorted({command["name"] for command in opencli["command"]["commands"]})

    missing_in_cli = [name for name in opencli_commands if name not in cli_commands]
    missing_in_opencli = [name for name in cli_commands if name not in opencli_commands]

    packaged_pairs = [
        ("skills/routing.json", "reverse_skill/data/routing.json"),
        ("skills/ida-reverse/references/ida-plugin-capabilities.json", "reverse_skill/data/ida-plugin-capabilities.json"),
    ]
    data_drift: List[str] = []
    for canonical_rel, packaged_rel in packaged_pairs:
        canonical = json.loads((repo_root / canonical_rel).read_text(encoding="utf-8"))
        packaged = json.loads((repo_root / packaged_rel).read_text(encoding="utf-8"))
        if canonical != packaged:
            data_drift.append(canonical_rel)

    documented_commands: List[str] = []
    for doc_name in ("README.md", "README_zh.md"):
        doc = (repo_root / doc_name).read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"reverse-skill\s+([a-z][a-z0-9-]*)", doc):
            name = match.group(1)
            if name not in documented_commands:
                documented_commands.append(name)
    unknown_documented = [name for name in documented_commands if name not in opencli_commands]

    checks = [
        {
            "name": "opencli_commands_exist_in_cli",
            "ok": not missing_in_cli,
            "detail": "missing in cli.py: " + ", ".join(missing_in_cli) if missing_in_cli else f"{len(opencli_commands)} commands",
        },
        {
            "name": "cli_commands_exist_in_opencli",
            "ok": not missing_in_opencli,
            "detail": "missing in opencli: " + ", ".join(missing_in_opencli) if missing_in_opencli else "ok",
        },
        {
            "name": "packaged_data_mirrors_canonical",
            "ok": not data_drift,
            "detail": "drift: " + ", ".join(data_drift) if data_drift else "ok",
        },
        {
            "name": "documented_commands_exist",
            "ok": not unknown_documented,
            "detail": "README documents unknown commands: " + ", ".join(unknown_documented) if unknown_documented else "ok",
        },
    ]
    failed = [check for check in checks if not check["ok"]]
    return {
        "status": "clean" if not failed else "findings",
        "checks": checks,
        "failures": failed,
    }


# --- Routing coherence ------------------------------------------------------

NON_PATH_FALLBACK_TARGETS = {"jshookmcp", "anything-analyzer", "agent-browser"}


def _module_refs_referenced(text: str) -> List[str]:
    """Extract backticked module references like `apk-reverse/` or `evolution/`."""
    refs: List[str] = []
    for match in re.finditer(r"`([A-Za-z0-9_-]+)/`", text):
        ref = match.group(1)
        if ref not in refs:
            refs.append(ref)
    return refs


def _module_exists(skills_root: Path, repo_root: Path, module: str) -> bool:
    for root in (skills_root, repo_root):
        if not root.is_dir():
            continue
        for candidate in root.iterdir():
            if not candidate.is_dir():
                continue
            if candidate.name.casefold() == module.casefold():
                return True
            # module-relative tier dirs: `validated/` == skills/field-journal/validated
            if (candidate / module).is_dir():
                return True
    return False


def routing_coherence(repo_root: Path | None = None) -> Dict[str, Any]:
    repo_root = repo_root or _resolve_repo_root()
    canonical_path = repo_root / "skills" / "routing.json"
    packaged_path = repo_root / "reverse_skill" / "data" / "routing.json"
    skills_root = repo_root / "skills"
    failures: List[str] = []

    try:
        canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "findings",
            "checks": [{"name": "routing_json_parses", "ok": False, "detail": str(exc)}],
            "failures": ["routing.json does not parse"],
        }
    try:
        packaged = json.loads(packaged_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "findings",
            "checks": [{"name": "packaged_routing_parses", "ok": False, "detail": str(exc)}],
            "failures": ["packaged routing.json does not parse"],
        }

    checks: List[Dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failures.append(name + ": " + detail)

    check("routing_json_parses", True, "ok")
    check("packaged_routing_parses", True, "ok")
    check("packaged_mirrors_canonical", canonical == packaged, "routing.json differs from packaged copy")

    routes = [route for route in canonical.get("macro_routes", []) if isinstance(route, dict)]
    check("macro_routes_present", bool(routes), "macro_routes is empty")

    for route in routes:
        route_id = str(route.get("id", ""))
        primary = str(route.get("primary_skill", ""))
        if primary:
            exists = (skills_root / primary).is_file()
            check(f"route:{route_id}:primary_skill", exists, primary)
        for edge in route.get("fallback_edges", []) or []:
            if not isinstance(edge, dict):
                continue
            goto = str(edge.get("goto", ""))
            if not goto:
                continue
            if goto.endswith(".md"):
                check(f"route:{route_id}:fallback:{goto}", (skills_root / goto).is_file(), goto)
            elif goto not in NON_PATH_FALLBACK_TARGETS:
                check(f"route:{route_id}:fallback:{goto}", False, "non-path fallback target not recognized: " + goto)

    for stage_list in (canonical.get("tool_stages") or {}).values():
        for stage in stage_list or []:
            if not isinstance(stage, dict):
                continue
            skill = str(stage.get("skill", ""))
            if skill.endswith(".md") and not (skills_root / skill).is_file():
                check("tool_stage:skill:" + skill, False, skill)

    for doc_name in ("routing.md", "routing_zh.md", "SKILL.md"):
        doc_path = skills_root / doc_name
        if not doc_path.is_file():
            continue
        text = doc_path.read_text(encoding="utf-8", errors="replace")
        for module in _module_refs_referenced(text):
            if not _module_exists(skills_root, repo_root, module):
                check(f"doc:{doc_name}:module:{module}", False, module)

    check("crosswalk_references_exist", True, "ok")
    crosswalk_path = repo_root / "reverse_skill" / "data" / "upstream-route-crosswalk.json"
    coverage_doc_path = repo_root / "docs" / "UPSTREAM-DOMAIN-COVERAGE.md"
    if crosswalk_path.is_file():
        crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8"))
        route_entries = crosswalk.get("routes") or {}
        status_counts: Dict[str, int] = {}
        expected_r_ids = {f"R{i}" for i in range(41)}
        missing_r_ids = sorted(expected_r_ids - set(route_entries.keys()))
        if missing_r_ids:
            check("crosswalk:covers_r0_to_r40", False, "missing entries: " + ", ".join(missing_r_ids))
        for r_id, entry in route_entries.items():
            status = entry.get("status")
            status_counts[status] = status_counts.get(status, 0) + 1
            mapped_route = entry.get("mapped_route")
            mapped_skill = entry.get("mapped_skill")
            if status not in {"adopted", "superseded", "rejected"}:
                check(f"crosswalk:{r_id}:status", False, "invalid status: " + str(status))
                continue
            if status in {"adopted", "superseded"}:
                if status == "adopted" and not mapped_route:
                    check(f"crosswalk:{r_id}:mapped_route", False, "adopted must map a route")
                if not mapped_route and not mapped_skill:
                    check(f"crosswalk:{r_id}:mapping", False, "adopted/superseded must map a route or skill")
                if mapped_skill:
                    check(f"crosswalk:{r_id}:skill", (skills_root / mapped_skill).is_file(), mapped_skill)
            elif status == "rejected" and mapped_route:
                check(f"crosswalk:{r_id}:rejected_mapping", False, "rejected domain must not map a route")

        for status in ("adopted", "superseded", "rejected"):
            check(
                f"crosswalk:count:{status}",
                status_counts.get(status, 0) > 0,
                f"{status}: {status_counts.get(status, 0)}",
            )

        # The coverage document must carry a machine-readable status marker
        # matching the crosswalk statistics (prevents doc drift).
        doc_marker_ok = False
        if coverage_doc_path.is_file():
            doc = coverage_doc_path.read_text(encoding="utf-8")
            marker = re.search(
                r"<!--\s*crosswalk-status:\s*adopted=(\d+)\s+superseded=(\d+)\s+rejected=(\d+)\s*-->",
                doc,
            )
            if marker:
                doc_counts = (int(marker.group(1)), int(marker.group(2)), int(marker.group(3)))
                actual_counts = (
                    status_counts.get("adopted", 0),
                    status_counts.get("superseded", 0),
                    status_counts.get("rejected", 0),
                )
                doc_marker_ok = doc_counts == actual_counts
                if not doc_marker_ok:
                    check(
                        "crosswalk:doc_status_marker",
                        False,
                        f"coverage doc says {doc_counts}, crosswalk has {actual_counts}",
                    )
            else:
                check("crosswalk:doc_status_marker", False, "coverage doc has no crosswalk-status marker")
        else:
            check("crosswalk:doc_status_marker", False, "coverage doc missing")

    failed = [check for check in checks if not check["ok"]]
    return {"status": "clean" if not failed else "findings", "checks": checks, "failures": failed}


# --- Aggregation ------------------------------------------------------------


def run_all(repo_root: Path | None = None, leak_path: str = "skills/field-journal") -> Dict[str, Any]:
    repo_root = repo_root or _resolve_repo_root()
    results = {
        "leak-scan": leak_scan(leak_path),
        "doc-facts": doc_facts(repo_root),
        "version": version_consistency(repo_root),
        "routing-coherence": routing_coherence(repo_root),
    }
    summary = {name: result["status"] for name, result in results.items()}
    failed = [name for name, status in summary.items() if status == "findings"]
    return {
        "status": "clean" if not failed else "findings",
        "summary": summary,
        "results": results,
        "failures": failed,
    }
