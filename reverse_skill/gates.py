"""Read-only repository checks and redacted leak findings."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List

from .errors import ToolOperationError


PACK_ROOT = Path(__file__).resolve().parent.parent


def _resolve_repo_root() -> Path:
    if not (PACK_ROOT / "pyproject.toml").is_file():
        raise ToolOperationError("repository gates require the complete skill or source checkout")
    return PACK_ROOT

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

_EMAIL_LOCAL = re.compile(r"[A-Za-z0-9._%+-]+")
_WORD_BOUNDARY = re.compile(r"\b")
_EMAIL = next(pattern["regex"] for pattern in LEAK_PATTERNS if pattern["name"] == "Email")


def _email_matches(line: str) -> Iterator[re.Match[str]]:
    # Try each local-part run once, rather than retrying all overlapping suffixes.
    consumed = 0
    for local in _EMAIL_LOCAL.finditer(line):
        if local.end() >= len(line) or line[local.end()] != "@" or local.end() <= consumed:
            continue
        boundary = _WORD_BOUNDARY.search(line, max(local.start(), consumed), local.end())
        if boundary is None or boundary.start() >= local.end():
            continue
        match = _EMAIL.match(line, boundary.start())
        if match:
            consumed = match.end()
            yield match


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
                matches = _email_matches(line) if pattern["name"] == "Email" else pattern["regex"].finditer(line)
                for match in matches:
                    if pattern["name"] == "Email" and _email_allowed(match.group(0)):
                        continue
                    findings.append(
                        {"file": str(file), "line": index, "kind": pattern["name"], "value": "[redacted]"}
                    )

    return {
        "status": "clean" if not findings else ("reported" if report_only else "findings"),
        "path": str(target),
        "scanned_files": len(files),
        "findings": findings,
        "report_only": report_only,
    }

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

    changelog_path = repo_root / "CHANGELOG.md"
    changelog_ok = changelog_path.is_file()
    if changelog_ok:
        changelog = changelog_path.read_text(encoding="utf-8")
        current = normalized["pyproject"]
        changelog_ok = ("## Unreleased" in changelog) or ("## [Unreleased]" in changelog) or (f"## [{current}]" in changelog) or (f"## [{values['pyproject']}]" in changelog)

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


def _result(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [check for check in checks if not check["ok"]]
    return {"status": "findings" if failures else "clean", "checks": checks, "failures": failures}


def doc_facts(repo_root: Path | None = None) -> dict[str, Any]:
    from .cli import cli

    root = repo_root or _resolve_repo_root()
    spec = json.loads((root / "reverse-skill.opencli.json").read_text(encoding="utf-8"))
    checks = []

    def compare(group, description, path):
        described = {entry["name"]: entry for entry in description.get("commands", [])}
        actual = getattr(group, "commands", {})
        checks.append({"name": path + ":commands", "ok": set(actual) == set(described),
                       "detail": {"missing_in_cli": sorted(set(described) - set(actual)),
                                  "missing_in_description": sorted(set(actual) - set(described))}})
        for name in set(actual) & set(described):
            if hasattr(actual[name], "commands"):
                compare(actual[name], described[name], path + " " + name)

    compare(cli, spec["command"], "reverse-skill")
    canonical = json.loads((root / "skills/routing.json").read_text(encoding="utf-8"))
    packaged = json.loads((root / "reverse_skill/data/routing.json").read_text(encoding="utf-8"))
    checks.append({"name": "packaged_routes_match", "ok": canonical == packaged,
                   "detail": "skills/routing.json vs reverse_skill/data/routing.json"})
    for filename in ("README.md", "README_zh.md"):
        text = (root / filename).read_text(encoding="utf-8")
        unknown = sorted(set(re.findall(r"reverse-skill\s+([a-z][a-z0-9-]*)", text)) - set(cli.commands))
        checks.append({"name": filename + ":commands", "ok": not unknown, "detail": unknown})
    return _result(checks)


def routing_coherence(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or _resolve_repo_root()
    data = json.loads((root / "skills/routing.json").read_text(encoding="utf-8"))
    routes = data.get("macro_routes", [])
    ids = [route["id"] for route in routes]
    checks = [{"name": "unique_routes", "ok": bool(ids) and len(set(ids)) == len(ids), "detail": ids}]
    for route in routes:
        paths = [route["primary_skill"], *(e.get("goto", "") for e in route.get("fallback_edges", []))]
        for path in paths:
            if not path.endswith(".md"):
                continue
            resolved = (root / "skills" / path).resolve()
            checks.append({"name": route["id"] + ":" + path,
                           "ok": resolved.is_relative_to(root.resolve()) and resolved.is_file(),
                           "detail": path})
    for aliases in ("route_aliases", "target_aliases"):
        unknown = sorted(set(data.get(aliases, {})) - set(ids))
        checks.append({"name": aliases + ":registered_routes", "ok": not unknown, "detail": unknown})
    return _result(checks)


def run_all(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or _resolve_repo_root()
    results = {"doc-facts": doc_facts(root), "version": version_consistency(root),
               "routing-coherence": routing_coherence(root)}
    failed = [name for name, value in results.items() if value["status"] != "clean"]
    return {"status": "findings" if failed else "clean", "results": results, "failures": failed}
