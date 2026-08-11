"""Canonical Python case package implementation: init + review.

This module implements the frozen case contracts declared in
``reverse_skill/data/case-contracts.json`` and documented in
``skills/ops/*.md``.  It is the Python main chain for ``case init`` and
``case review``; upstream ``case-init.sh`` / ``review_case.py`` are
behavioral references only and are not invoked.

Guarantees:
- network profile normalization with aliases; unknown modes fail (exit 2 via CLI).
- artifact SHA-256 fixity verification (``sha256:<64hex>`` or bare ``64hex``).
- path escape protection: an ``artifact_path`` that resolves outside the case
  root is an error, never a warning.
- stable JSON envelope and exit codes through the package CLI.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .routing import build_plan

PACKAGE_ROOT = Path(__file__).resolve().parent
CONTRACTS_PATH = PACKAGE_ROOT / "data" / "case-contracts.json"

# --- Compiled field/id patterns -------------------------------------------

FIELD_LINE = re.compile(r"^\s*-\s+([A-Za-z0-9_]+):\s*(.*)$")
SECTION_HEADING = re.compile(r"^#{2,6}\s+(.+?)\s*$")
EVIDENCE_HEADING = re.compile(r"^###\s+(E-[A-Za-z0-9][A-Za-z0-9_-]*)\b", re.MULTILINE)
FINDING_HEADING = re.compile(r"^###\s+(F-[A-Za-z0-9][A-Za-z0-9_-]*)\b", re.MULTILINE)
PATH_HEADING = re.compile(r"^###\s+(P-[A-Za-z0-9][A-Za-z0-9_-]*)\b", re.MULTILINE)

_EVIDENCE_ID = re.compile(r"\bE-[A-Za-z0-9][A-Za-z0-9_-]*\b")
_WORKITEM_ID = re.compile(r"\bWI-[A-Za-z0-9][A-Za-z0-9_-]*\b")

_CASE_NAME_INVALID = re.compile(r"[/:\\*?\"<>|]|[\x00-\x1f]")
_CASE_NAME_TRAILING = re.compile(r"[.\s]$")

OFFLINE_MARKERS = ("offline", "离线", "not applicable")


class CaseContractError(ValueError):
    """Raised when an input violates a frozen case contract."""


class CasePackageError(RuntimeError):
    """Raised when a case package cannot be created or reviewed."""


# --- Contract loading -----------------------------------------------------


def load_contracts() -> Dict[str, Any]:
    with CONTRACTS_PATH.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise CasePackageError("case-contracts.json root must be an object")
    return value


def enum_values(name: str) -> List[str]:
    value = load_contracts()["enums"][name]
    return [str(item) for item in value]


def id_pattern(name: str) -> re.Pattern[str]:
    return re.compile(load_contracts()["id_patterns"][name])


# --- Network profile normalization ---------------------------------------


def normalize_network_profile(value: str) -> str:
    """Normalize a network profile to a canonical mode or raise.

    Canonical: offline | lab_only | authorized_target_only | unrestricted_lab.
    Aliases: lab, authorized, auth, offline_only (frozen contract).
    """
    raw = str(value or "").strip().lower()
    if not raw:
        raise CaseContractError("network profile is required")
    contracts = load_contracts()
    canonical = contracts["enums"]["network_modes"]
    if raw in canonical:
        return raw
    aliases = contracts["enums"]["network_mode_aliases"]
    if raw in aliases:
        return str(aliases[raw])
    raise CaseContractError(
        "unsupported network profile: "
        + value
        + " (allowed: "
        + ", ".join(canonical)
        + "; aliases: lab, authorized, auth, offline_only)"
    )


# --- Case name validation -------------------------------------------------


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower())
    slug = re.sub(r"^-+|-+$", "", slug)
    return (slug[:limit] or "case").rstrip("-")


def validate_case_name(name: str) -> str:
    """Validate a case directory name. Returns the validated name."""
    value = str(name or "")
    if not value:
        raise CaseContractError("case name is required")
    if len(value) > 80:
        raise CaseContractError("case name must be at most 80 characters")
    if not value[0].isalnum():
        raise CaseContractError("case name must begin with a letter or number")
    if _CASE_NAME_INVALID.search(value):
        raise CaseContractError(
            "case name must not contain path separators, wildcards, or control characters"
        )
    if _CASE_NAME_TRAILING.search(value):
        raise CaseContractError("case name must not end with a dot or space")
    return value


# --- Markdown helpers -----------------------------------------------------


def field_value(text: str, name: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = FIELD_LINE.match(line)
        if not match or match.group(1) != name:
            continue
        value = match.group(2).strip()
        if value != "|":
            return value
        block: List[str] = []
        for continuation in lines[index + 1 :]:
            if FIELD_LINE.match(continuation):
                break
            if SECTION_HEADING.match(continuation):
                break
            if continuation.strip():
                block.append(continuation.strip())
        return "\n".join(block).strip()
    return ""


def section_text(text: str, title: str) -> str:
    pattern = re.compile(
        r"(?ms)^##\s+" + re.escape(title) + r"\s*$\n?(.*?)(?=^##\s|\Z)"
    )
    match = pattern.search(text)
    return match.group(1) if match else ""


def ids_in(value: str, pattern: re.Pattern[str]) -> List[str]:
    return sorted(set(pattern.findall(value or "")))


def split_table_row(line: str) -> List[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def issue(issues: List[Dict[str, Any]], level: str, code: str, message: str, path: str = "") -> None:
    issues.append({"level": level, "code": code, "message": message, "path": path})


def relative_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


# --- Scope ----------------------------------------------------------------


def parse_scope(root: Path, issues: List[Dict[str, Any]], strict: bool) -> Dict[str, Any]:
    path = root / "scope.md"
    result = {"auth_status": "", "network_mode": "", "ready_for_act": "", "assets": []}
    if not path.is_file():
        issue(issues, "error", "scope.missing", "scope.md is missing", "scope.md")
        return result

    text = path.read_text(encoding="utf-8-sig")
    auth = section_text(text, "auth")
    scope_section = section_text(text, "in_scope")
    network = section_text(text, "network_profile")
    signoff = section_text(text, "signoff")
    result["auth_status"] = field_value(auth, "status").lower()
    result["network_mode"] = field_value(network, "mode").lower()
    result["ready_for_act"] = field_value(signoff, "ready_for_act").lower()

    # Only a top-level "- field:" ends the assets block. Indented Windows
    # paths such as "  - D:\repo" contain a colon but are asset values.
    assets_match = re.search(
        r"(?ms)^\s*-\s+assets:\s*\n(?P<body>.*?)(?=^-\s+[A-Za-z0-9_]+:|\Z)",
        scope_section,
    )
    if assets_match:
        result["assets"] = [
            line.strip()[2:].strip()
            for line in assets_match.group("body").splitlines()
            if re.match(r"^\s+-\s+\S+", line) and line.strip()[2:].strip() != "[]"
        ]

    auth_statuses = set(enum_values("auth_statuses"))
    network_modes = set(enum_values("network_modes"))
    if not result["auth_status"]:
        issue(issues, "error", "scope.auth_missing", "auth.status is missing", "scope.md")
    elif result["auth_status"] not in auth_statuses:
        issue(issues, "error", "scope.auth_invalid", "unsupported auth.status: " + result["auth_status"], "scope.md")

    if not result["network_mode"]:
        issue(issues, "error", "scope.network_missing", "network_profile.mode is missing", "scope.md")
    elif result["network_mode"] not in network_modes:
        issue(issues, "error", "scope.network_invalid", "unsupported network mode: " + result["network_mode"], "scope.md")

    if not result["ready_for_act"]:
        issue(issues, "error", "scope.ready_missing", "signoff.ready_for_act is missing", "scope.md")
    elif result["ready_for_act"] not in {"true", "false"}:
        issue(issues, "error", "scope.ready_invalid", "ready_for_act must be true or false", "scope.md")

    if result["network_mode"] != "offline" and not result["assets"]:
        issue(issues, "error", "scope.assets_missing", "in_scope.assets is empty for a network case", "scope.md")

    if result["auth_status"] != "granted" or result["ready_for_act"] != "true":
        message = "scope is not ready for target ACT"
        if strict and result["network_mode"] != "offline":
            issue(issues, "error", "scope.not_ready", message, "scope.md")
        else:
            issue(issues, "warning", "scope.not_ready", message, "scope.md")
    return result


# --- Work items -----------------------------------------------------------


def parse_workitems(root: Path, issues: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Tuple[str, str]]]:
    path = root / "workitems.md"
    records: Dict[str, Any] = {}
    references: List[Tuple[str, str]] = []
    if not path.is_file():
        issue(issues, "error", "workitems.missing", "workitems.md is missing", "workitems.md")
        return records, references

    workitem_pattern = id_pattern("workitem")
    workitem_statuses = set(enum_values("workitem_statuses"))
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        cells = split_table_row(line)
        if len(cells) < 8 or not workitem_pattern.fullmatch(cells[0]):
            continue
        workitem_id = cells[0]
        status = cells[5].lower()
        if status not in workitem_statuses:
            issue(
                issues,
                "error",
                "workitem.status",
                "unsupported work item status: " + status,
                "workitems.md:" + str(line_number),
            )
        evidence_ids = ids_in(cells[6], _EVIDENCE_ID)
        records[workitem_id] = {"status": status, "evidence_ids": evidence_ids}
        references.extend((evidence_id, "workitems.md:" + str(line_number)) for evidence_id in evidence_ids)

    if not records:
        issue(issues, "warning", "workitems.empty", "no work item rows were found", "workitems.md")
    return records, references


# --- Timeline -------------------------------------------------------------


def parse_timeline(root: Path, issues: List[Dict[str, Any]]) -> Tuple[int, List[Tuple[str, str]]]:
    path = root / "timeline.md"
    references: List[Tuple[str, str]] = []
    events = 0
    if not path.is_file():
        issue(issues, "error", "timeline.missing", "timeline.md is missing", "timeline.md")
        return events, references

    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("## ") or "|" not in line:
            continue
        events += 1
        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            if lines[next_index].startswith("## "):
                end = next_index
                break
        body = "\n".join(lines[index:end])
        evidence_ids = ids_in(field_value(body, "evidence_ids"), _EVIDENCE_ID)
        references.extend((evidence_id, "timeline.md:" + str(index + 1)) for evidence_id in evidence_ids)

    if events == 0:
        issue(issues, "warning", "timeline.empty", "no append-only timeline events were found", "timeline.md")
    return events, references


# --- Evidence + artifact fixity -------------------------------------------


def normalize_hash(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized[7:]
    if re.fullmatch(r"[0-9a-f]{64}", normalized):
        return normalized
    return ""


def resolve_artifact(root: Path, artifact_path: str) -> Optional[Path]:
    """Resolve an artifact path inside the case root, or None when it escapes.

    Escape protection is fail-closed: absolute paths outside the root and
    ``..`` traversal that leaves the root both resolve to None.
    """
    if not artifact_path:
        return None
    raw = str(artifact_path).strip()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact(
    root: Path,
    artifact_path: str,
    expected_hash: str,
    issues: List[Dict[str, Any]],
    display_path: str,
) -> None:
    if not artifact_path:
        issue(issues, "warning", "artifact.path_missing", "content_hash is recorded without artifact_path", display_path)
        return
    candidate = resolve_artifact(root, artifact_path)
    if candidate is None:
        issue(issues, "error", "artifact.outside_case", "artifact_path escapes the case root", display_path)
        return
    if not candidate.is_file():
        issue(issues, "error", "artifact.missing", "artifact_path does not exist", display_path)
        return
    digest = sha256_file(candidate)
    if digest != expected_hash:
        issue(issues, "error", "artifact.hash_mismatch", "artifact SHA-256 does not match content_hash", display_path)


def parse_evidence(
    root: Path,
    workitems: Dict[str, Any],
    issues: List[Dict[str, Any]],
    verify_hashes: bool,
) -> Tuple[Dict[str, Any], List[Tuple[str, str]]]:
    evidence_root = root / "evidence"
    records: Dict[str, Any] = {}
    references: List[Tuple[str, str]] = []
    if not evidence_root.is_dir():
        issue(issues, "error", "evidence.dir_missing", "evidence directory is missing", "evidence")
        return records, references

    evidence_files = sorted(path for path in evidence_root.glob("E-*.md") if path.name != "INDEX.md")
    if not evidence_files:
        issue(issues, "warning", "evidence.empty", "no Evidence records were found", "evidence")

    severities = set(enum_values("severities"))
    evidence_statuses = set(enum_values("evidence_statuses"))
    for path in evidence_files:
        evidence_id = path.stem
        text = path.read_text(encoding="utf-8-sig")
        heading = EVIDENCE_HEADING.search(text)
        if not heading:
            issue(issues, "error", "evidence.heading_missing", "Evidence record has no matching heading", relative_path(root, path))
        elif heading.group(1) != evidence_id:
            issue(issues, "error", "evidence.heading_mismatch", "Evidence heading does not match its filename", relative_path(root, path))

        severity = field_value(text, "severity").lower()
        status = field_value(text, "status").lower()
        repro_command = field_value(text, "repro_command")
        notes = field_value(text, "notes").lower()
        linked_workitems = ids_in(field_value(text, "linked_workitem"), _WORKITEM_ID)
        content_hash_value = field_value(text, "content_hash")
        artifact_path = field_value(text, "artifact_path")
        if severity not in severities:
            issue(issues, "error", "evidence.severity", "unsupported severity: " + severity, relative_path(root, path))
        if status not in evidence_statuses:
            issue(issues, "error", "evidence.status", "unsupported status: " + status, relative_path(root, path))
        offline_note = any(marker in notes for marker in OFFLINE_MARKERS)
        if not repro_command or (repro_command.lower() in {"n/a", "n/a_re"} and not offline_note):
            issue(
                issues,
                "error",
                "evidence.repro_missing",
                "Evidence requires a reproducible command or documented offline limitation",
                relative_path(root, path),
            )
        expected_hash = ""
        if content_hash_value.lower() != "n/a":
            expected_hash = normalize_hash(content_hash_value)
            if not expected_hash:
                issue(issues, "error", "evidence.hash_invalid", "content_hash must be SHA-256", relative_path(root, path))
        if verify_hashes and expected_hash:
            verify_artifact(root, artifact_path, expected_hash, issues, relative_path(root, path))
        for workitem_id in linked_workitems:
            if workitem_id not in workitems:
                issue(issues, "error", "evidence.workitem_missing", "linked work item does not exist: " + workitem_id, relative_path(root, path))
        records[evidence_id] = {"severity": severity, "status": status, "artifact_path": artifact_path}

    return records, references


# --- Reports --------------------------------------------------------------


def report_sections(text: str, heading_pattern: re.Pattern[str]) -> List[Tuple[str, str]]:
    matches = list(heading_pattern.finditer(text))
    sections: List[Tuple[str, str]] = []
    for match in matches:
        end = len(text)
        for next_match in re.finditer(r"(?m)^#{1,3}\s+", text[match.end() :]):
            end = match.end() + next_match.start()
            break
        sections.append((match.group(1), text[match.start() : end]))
    return sections


def parse_reports(root: Path, issues: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Tuple[str, str]]]:
    finding_records: List[Dict[str, Any]] = []
    path_records: List[Dict[str, Any]] = []
    references: List[Tuple[str, str]] = []
    report_root = root / "report"
    report_files = sorted(report_root.rglob("*.md")) if report_root.is_dir() else []
    if not report_files:
        issue(issues, "warning", "report.missing", "no Markdown report was found", "report")
        return finding_records, path_records, references

    finding_statuses = set(enum_values("finding_statuses"))
    path_types = set(enum_values("path_types"))
    for report_path in report_files:
        text = report_path.read_text(encoding="utf-8-sig")
        for finding_id, body in report_sections(text, FINDING_HEADING):
            status = field_value(body, "status").lower()
            confidence = field_value(body, "confidence").lower()
            evidence_ids = ids_in(field_value(body, "evidence_ids"), _EVIDENCE_ID)
            required = ("severity", "evidence_ids", "confidence", "location", "status")
            for field in required:
                if not field_value(body, field):
                    issue(
                        issues,
                        "error",
                        "finding.field_missing",
                        finding_id + " is missing " + field,
                        relative_path(root, report_path),
                    )
            if status not in finding_statuses:
                issue(issues, "error", "finding.status", finding_id + " has unsupported status", relative_path(root, report_path))
            if status == "validated" and confidence == "low":
                issue(issues, "error", "finding.confidence", finding_id + " is validated with low confidence", relative_path(root, report_path))
            if not evidence_ids:
                issue(issues, "error", "finding.evidence_missing", finding_id + " has no evidence_ids", relative_path(root, report_path))
            references.extend((evidence_id, relative_path(root, report_path)) for evidence_id in evidence_ids)
            finding_records.append({"id": finding_id, "status": status, "evidence_ids": evidence_ids, "path": relative_path(root, report_path)})

        for path_id, body in report_sections(text, PATH_HEADING):
            path_type = field_value(body, "path_type").lower()
            evidence_ids = ids_in(body, _EVIDENCE_ID)
            if path_type not in path_types:
                issue(issues, "error", "path.type", path_id + " has unsupported path_type", relative_path(root, report_path))
            if not evidence_ids:
                issue(issues, "error", "path.evidence_missing", path_id + " has no evidence reference", relative_path(root, report_path))
            references.extend((evidence_id, relative_path(root, report_path)) for evidence_id in evidence_ids)
            path_records.append({"id": path_id, "path_type": path_type, "evidence_ids": evidence_ids, "path": relative_path(root, report_path)})
    return finding_records, path_records, references


# --- Traceability ---------------------------------------------------------


def build_traceability(evidence_ids: Iterable[str], references: Sequence[Tuple[str, str]]) -> Dict[str, Dict[str, int]]:
    graph = {evidence_id: {"workitems": 0, "timeline": 0, "reports": 0} for evidence_id in sorted(evidence_ids)}
    for evidence_id, source in references:
        if evidence_id not in graph:
            continue
        if source.startswith("workitems.md:"):
            graph[evidence_id]["workitems"] += 1
        elif source.startswith("timeline.md:"):
            graph[evidence_id]["timeline"] += 1
        else:
            graph[evidence_id]["reports"] += 1
    return graph


# --- Review ---------------------------------------------------------------


def review_case(case_root: str, strict: bool = False, verify_hashes: bool = False) -> Dict[str, Any]:
    root = Path(case_root).expanduser().resolve()
    issues: List[Dict[str, Any]] = []
    if not root.is_dir():
        issue(issues, "error", "case.missing", "case root does not exist", str(root))
        return {
            "status": "FAIL",
            "case_root": str(root),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {"errors": 1, "warnings": 0, "evidence": 0, "workitems": 0, "timeline_events": 0, "findings": 0, "paths": 0},
            "issues": issues,
            "traceability": {},
        }

    workitems, workitem_refs = parse_workitems(root, issues)
    timeline_events, timeline_refs = parse_timeline(root, issues)
    scope = parse_scope(root, issues, strict)
    evidence, evidence_refs = parse_evidence(root, workitems, issues, verify_hashes)
    findings, paths, report_refs = parse_reports(root, issues)
    references = workitem_refs + timeline_refs + evidence_refs + report_refs

    for evidence_id, source in references:
        if evidence_id not in evidence:
            issue(issues, "error", "reference.unknown_evidence", "reference points to missing Evidence: " + evidence_id, source)

    traceability = build_traceability(evidence, references)
    for evidence_id, links in traceability.items():
        if not any(links.values()):
            issue(
                issues,
                "warning",
                "evidence.unlinked",
                "Evidence is not referenced by a work item, timeline, or report",
                "evidence/" + evidence_id + ".md",
            )

    errors = sum(1 for item in issues if item["level"] == "error")
    warnings = sum(1 for item in issues if item["level"] == "warning")
    status = "FAIL" if errors or (strict and warnings) else "WARN" if warnings else "PASS"
    return {
        "status": status,
        "case_root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "evidence": len(evidence),
            "workitems": len(workitems),
            "timeline_events": timeline_events,
            "findings": len(findings),
            "paths": len(paths),
        },
        "issues": issues,
        "traceability": traceability,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Case review",
        "",
        "- status: " + report["status"],
        "- case_root: " + report["case_root"],
        "- generated_at: " + report["generated_at"],
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in ("errors", "warnings", "evidence", "workitems", "timeline_events", "findings", "paths"):
        lines.append("| " + key + " | " + str(summary[key]) + " |")

    lines.extend(["", "## Checks", "", "| Level | Code | Location | Detail |", "|---|---|---|---|"])
    if report["issues"]:
        for item in report["issues"]:
            location = item["path"].replace("|", "\\|")
            detail = item["message"].replace("|", "\\|")
            lines.append("| " + item["level"] + " | " + item["code"] + " | " + location + " | " + detail + " |")
    else:
        lines.append("| pass | none | n/a | No review issues found |")

    lines.extend(["", "## Traceability", "", "| Evidence | Work items | Timeline | Reports |", "|---|---:|---:|---:|"])
    if report["traceability"]:
        for evidence_id, links in report["traceability"].items():
            lines.append(
                "| " + evidence_id + " | " + str(links["workitems"]) + " | " + str(links["timeline"]) + " | " + str(links["reports"]) + " |"
            )
    else:
        lines.append("| n/a | 0 | 0 | 0 |")
    return "\n".join(lines) + "\n"


# --- Init -----------------------------------------------------------------


def _route_primary(hint: str) -> Dict[str, Any]:
    """Resolve the primary skill through the packaged Python router."""
    try:
        plan = build_plan({"task": hint})
    except Exception as exc:  # pragma: no cover - defensive; router is deterministic
        return {"skill": "reverse-engineering/SKILL.md", "route_id": "no_route", "route_status": "error", "note": str(exc)}
    route = plan.get("route") or {}
    base_id = str(route.get("base_id") or route.get("id") or "")
    skill = str(route.get("skill") or "")
    status = str(plan.get("status") or "")
    if status == "no_route" or not base_id or not skill:
        return {"skill": "reverse-engineering/SKILL.md", "route_id": "no_route", "route_status": status}
    return {"skill": skill, "route_id": base_id, "route_status": status}


def init_case(
    hint: str,
    case_name: Optional[str] = None,
    *,
    preset: Optional[str] = None,
    network_profile: Optional[str] = None,
    auth_status: Optional[str] = None,
    auth_basis: Optional[str] = None,
    evidence_of_auth: Optional[str] = None,
    target_url: Optional[str] = None,
    sample: Optional[str] = None,
    in_scope_assets: Sequence[str] = (),
    package_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a ``work/<case>/`` package per the frozen case contracts."""
    if not hint:
        raise CaseContractError("hint is required")

    contracts = load_contracts()
    presets = contracts["presets"]
    preset_name = None
    if preset:
        preset_key = str(preset).strip().lower()
        preset_name = None
        for key, definition in presets.items():
            if preset_key == key or preset_key in definition.get("aliases", []):
                preset_name = key
                break
        if preset_name is None:
            raise CaseContractError(
                "unknown preset: " + str(preset) + " (allowed: " + ", ".join(sorted(presets.keys())) + ")"
            )

    name = case_name or (slugify(hint) if hint else "case")
    name = validate_case_name(name)

    resolved_network: Optional[str] = None
    if network_profile:
        resolved_network = normalize_network_profile(network_profile)

    resolved_auth_status = "pending"
    if auth_status:
        candidate = str(auth_status).strip().lower()
        if candidate not in enum_values("auth_statuses"):
            raise CaseContractError("unsupported auth status: " + str(auth_status))
        resolved_auth_status = candidate
    resolved_auth_basis = auth_basis or "unknown"
    resolved_evidence_auth = evidence_of_auth or "FILL_ME"
    if preset_name:
        definition = presets[preset_name]
        resolved_auth_status = definition["auth_status"]
        resolved_auth_basis = definition["auth_basis"]
        resolved_network = definition["network_mode"]
        resolved_evidence_auth = definition["evidence_of_auth"]

    assets: List[str] = []
    if target_url:
        assets.append(target_url)
    if sample:
        assets.append(sample)
    for asset in in_scope_assets:
        if asset and asset not in assets:
            assets.append(asset)
    if not assets and re.search(r"https?://([^:\s/]+)", hint or ""):
        assets.append("https://" + re.search(r"https?://([^:\s/]+)", hint).group(1) + "/")

    if resolved_network is None:
        if resolved_auth_status == "granted" and assets and not sample:
            resolved_network = "authorized_target_only"
        else:
            resolved_network = "offline"

    ready = False
    if resolved_auth_status == "granted":
        if resolved_network == "offline":
            if sample and assets:
                ready = True
        elif assets:
            ready = True

    root_dir = Path(package_root or os.getcwd()).expanduser()
    case_root = root_dir / "work" / name
    try:
        case_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise CasePackageError("case already exists: " + str(case_root)) from exc
    for directory in ("evidence", "notes", "report"):
        (case_root / directory).mkdir(parents=True, exist_ok=True)

    primary = _route_primary(hint)
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    assets_block = "\n".join("  - " + asset for asset in assets) if assets else "  []"
    ready_str = "true" if ready else "false"
    check_auth = "[x]" if resolved_auth_status == "granted" else "[ ]"
    check_scope = "[x]" if (assets or resolved_network == "offline") else "[ ]"
    check_net = "[x]" if resolved_network else "[ ]"

    scope_md = f"""# Case Scope

## meta
- case_id: {name}
- created: {created}
- operator: local
- primary_skill: {primary['skill']}
- primary_id: {primary['route_id']}
- lead_role: lead
- specialist_roles: []
- hint: {hint}
- preset: {preset_name or 'none'}

## auth
- status: {resolved_auth_status}
- basis: {resolved_auth_basis}
- evidence_of_auth: {resolved_evidence_auth}
- MUST NOT proceed if status != granted

## in_scope
- assets:
{assets_block}
- surfaces: []
- activities: []

## out_of_scope
- assets: []
- activities: [dos, phishing_real_users, unrestricted_exfil]

## network_profile
- mode: {resolved_network}
- notes: |
    offline | lab_only | authorized_target_only | unrestricted_lab
    Change mode only after auth.status = granted.
    Presets: offline-sample | ctf-public | own-system

## deliverables
- report: true
- field_journal: true
- diagrams: true
- timeline: true

## constraints
- timebox: {{}}
- stealth: low
- data_handling: anonymize

## signoff
- ready_for_act: {ready_str}
- checklist:
  - {check_auth} auth.status = granted
  - {check_scope} in_scope.assets non-empty OR offline sample path set
  - {check_net} network_profile.mode chosen
  - [ ] out_of_scope reviewed
  - [ ] roles assigned (see skills/ops/role-map.md)

## ops_refs
- skills/ops/scope-contract.md
- skills/ops/evidence-finding-path.md
- skills/ops/timeline-workitem.md
"""

    if ready:
        timeline_summary = "case directory created; scope ready_for_act=true"
        timeline_next = "open PRIMARY SKILL.md and ACT within scope"
        readme_body = f"""1. Scope is ready_for_act=true (auth granted + in_scope set)
2. Open primary skill: skills/{primary['skill']}
3. Append `timeline.md`; update `workitems.md`
4. Append Evidence under `evidence/`
5. Promote findings with Evidence chain (skills/ops/evidence-finding-path.md)
6. Report via docs-generator; journal via field-journal
"""
    else:
        timeline_summary = "case directory created; scope pending auth"
        timeline_next = "fill scope auth + in_scope; set ready_for_act"
        readme_body = f"""1. Edit `scope.md` — set auth.status=granted and in_scope
   - or re-run: `reverse-skill case init --hint "..." --preset offline-sample --sample ./sample.bin`
   - or: `--preset ctf-public --target-url https://...`
2. Set ready_for_act when checklist complete
3. Open primary skill: skills/{primary['skill']}
4. Append `timeline.md`; update `workitems.md`
5. Promote findings with Evidence chain (skills/ops/evidence-finding-path.md)
6. Report via docs-generator; journal via field-journal
"""

    timeline_md = f"""# Timeline (append-only)

## {created} | lead | init
- action: case-init
- command_or_ref: reverse-skill case init
- result_summary: {timeline_summary}
- artifacts: [scope.md, workitems.md]
- evidence_ids: []
- next: {timeline_next}
"""

    workitems_md = """# Work Items

| ID | title | role | targets | surface | status | evidence | notes |
|----|-------|------|---------|---------|--------|----------|-------|
| WI-001 | Establish scope and auth | lead | case | process | in_progress | | |

## Coverage
- [ ] Recon/analysis complete for in_scope assets
- [ ] Critical/High candidates triaged (or N/A for pure RE)
- [ ] Validated findings have Evidence (E-*)
- [ ] Path documented (attack/call/solve)
- [ ] Timeline continuous across major phases
- [ ] Report via docs-generator
- [ ] field-journal anonymized

## Refs
- skills/ops/timeline-workitem.md
- skills/ops/evidence-finding-path.md
"""

    (case_root / "scope.md").write_text(scope_md, encoding="utf-8")
    (case_root / "timeline.md").write_text(timeline_md, encoding="utf-8")
    (case_root / "workitems.md").write_text(workitems_md, encoding="utf-8")
    (case_root / "README.md").write_text("# Case " + name + "\n\n" + readme_body, encoding="utf-8")

    return {
        "status": "created",
        "case_root": str(case_root),
        "case_name": name,
        "ready_for_act": ready,
        "primary_skill": primary["skill"],
        "primary_id": primary["route_id"],
        "route_status": primary["route_status"],
        "auth_status": resolved_auth_status,
        "network_profile": resolved_network,
        "created": created,
        "files": ["scope.md", "timeline.md", "workitems.md", "README.md"],
    }
