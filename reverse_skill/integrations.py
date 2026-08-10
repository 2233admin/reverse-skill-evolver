from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from .errors import EnvironmentUnavailable, ToolOperationError


class ToolClient(Protocol):
    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Mapping[str, Any]: ...


def _distribution_version(*names: str) -> str | None:
    for name in names:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def integration_inventory() -> list[dict[str, Any]]:
    """Return honest local availability and the implemented IDA bridge boundary."""
    yara_available = _module_available("yara")
    definitions = [
        {
            "name": "yara",
            "available": yara_available,
            "version": _distribution_version("yara-python") if yara_available else None,
            "entry": "python:yara" if yara_available else None,
            "support": "ready",
            "idaBridge": ["scan", "annotate-unique-byte-matches"],
        },
        {
            "name": "capa",
            "available": bool(shutil.which("capa") or _module_available("capa")),
            "version": _distribution_version("flare-capa", "capa"),
            "entry": shutil.which("capa") or ("python:capa" if _module_available("capa") else None),
            "support": "discovery_only",
            "idaBridge": [],
        },
        {
            "name": "floss",
            "available": bool(shutil.which("floss") or _module_available("floss")),
            "version": _distribution_version("flare-floss"),
            "entry": shutil.which("floss") or ("python:floss" if _module_available("floss") else None),
            "support": "discovery_only",
            "idaBridge": [],
        },
        {
            "name": "radare2",
            "available": bool(shutil.which("r2") and shutil.which("rabin2")),
            "version": None,
            "entry": shutil.which("rabin2") or shutil.which("r2"),
            "support": "discovery_only",
            "idaBridge": [],
        },
        {
            "name": "bindiff",
            "available": bool(shutil.which("bindiff")),
            "version": None,
            "entry": shutil.which("bindiff"),
            "support": "discovery_only",
            "idaBridge": [],
        },
        {
            "name": "diaphora",
            "available": bool(shutil.which("diaphora") or _module_available("diaphora")),
            "version": _distribution_version("diaphora"),
            "entry": shutil.which("diaphora") or ("python:diaphora" if _module_available("diaphora") else None),
            "support": "discovery_only",
            "idaBridge": [],
        },
        {
            "name": "x64dbg",
            "available": bool(shutil.which("x64dbg") or shutil.which("x96dbg")),
            "version": None,
            "entry": shutil.which("x64dbg") or shutil.which("x96dbg"),
            "support": "discovery_only",
            "idaBridge": [],
        },
        {
            "name": "windbg",
            "available": bool(shutil.which("windbg") or shutil.which("cdb")),
            "version": None,
            "entry": shutil.which("windbg") or shutil.which("cdb"),
            "support": "discovery_only",
            "idaBridge": [],
        },
    ]
    return definitions


def _instance_record(instance: Any) -> tuple[dict[str, Any], bytes]:
    data = bytes(getattr(instance, "matched_data", b""))
    matched_length = int(getattr(instance, "matched_length", len(data)))
    record = {
        "offset": int(getattr(instance, "offset")),
        "matchedLength": matched_length,
        "dataHex": data[:256].hex(),
        "dataTruncated": len(data) > 256,
    }
    xor_key = int(getattr(instance, "xor_key", 0))
    if xor_key:
        record["xorKey"] = xor_key
    return record, data


def _normalize_match(match: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    strings: list[dict[str, Any]] = []
    annotation_inputs: list[dict[str, Any]] = []
    for string_match in getattr(match, "strings", []):
        if isinstance(string_match, tuple):
            offset, identifier, data = string_match
            raw = bytes(data)
            record = {
                "identifier": str(identifier),
                "instances": [
                    {
                        "offset": int(offset),
                        "matchedLength": len(raw),
                        "dataHex": raw[:256].hex(),
                        "dataTruncated": len(raw) > 256,
                    }
                ],
            }
            annotation_inputs.append(
                {"identifier": str(identifier), "offset": int(offset), "data": raw}
            )
            strings.append(record)
            continue

        identifier = str(getattr(string_match, "identifier", ""))
        instances: list[dict[str, Any]] = []
        for instance in getattr(string_match, "instances", []):
            record, raw = _instance_record(instance)
            instances.append(record)
            annotation_inputs.append(
                {"identifier": identifier, "offset": record["offset"], "data": raw}
            )
        strings.append({"identifier": identifier, "instances": instances})

    normalized = {
        "rule": str(getattr(match, "rule", "")),
        "namespace": str(getattr(match, "namespace", "default")),
        "tags": list(getattr(match, "tags", [])),
        "meta": dict(getattr(match, "meta", {})),
        "strings": strings,
    }
    for value in annotation_inputs:
        value["rule"] = normalized["rule"]
        value["namespace"] = normalized["namespace"]
    return normalized, annotation_inputs


def scan_yara(
    target: Path,
    rule_paths: Iterable[Path],
    timeout: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        yara = importlib.import_module("yara")
    except ImportError as exc:
        raise EnvironmentUnavailable(
            "YARA integration requires yara-python; install it in the reverse-skill Python environment"
        ) from exc

    paths = [path.resolve() for path in rule_paths]
    namespaces = {f"rules_{index}": str(path) for index, path in enumerate(paths)}
    try:
        rules = yara.compile(filepaths=namespaces)
        raw_matches = rules.match(str(target.resolve()), timeout=max(1, int(timeout)))
    except Exception as exc:
        raise ToolOperationError(f"YARA scan failed: {exc}") from exc

    matches: list[dict[str, Any]] = []
    annotation_inputs: list[dict[str, Any]] = []
    string_count = 0
    instance_count = 0
    for raw_match in raw_matches:
        normalized, inputs = _normalize_match(raw_match)
        matches.append(normalized)
        annotation_inputs.extend(inputs)
        string_count += len(normalized["strings"])
        instance_count += sum(len(item["instances"]) for item in normalized["strings"])

    return (
        {
            "target": str(target.resolve()),
            "rules": [str(path) for path in paths],
            "matches": matches,
            "summary": {
                "ruleMatches": len(matches),
                "stringMatches": string_count,
                "instanceMatches": instance_count,
            },
        },
        annotation_inputs,
    )


def _structured_content(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("structuredContent")
    return value if isinstance(value, Mapping) else result


def _same_path(left: str, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(str(right.resolve()))


def _normalize_pattern(pattern: str) -> str:
    return " ".join(pattern.upper().split())


def annotate_yara_matches(
    client: ToolClient,
    database: str,
    target: Path,
    instances: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    health = _structured_content(client.call_tool("server_health", {"database": database}))
    active_path = str(health.get("input_path") or "")
    if not active_path or not _same_path(active_path, target):
        raise ToolOperationError(
            f"refusing to annotate a different IDA database: target={target.resolve()} active={active_path or '<unknown>'}"
        )

    skipped: list[dict[str, Any]] = []
    by_pattern: dict[str, list[Mapping[str, Any]]] = {}
    for instance in instances:
        raw = bytes(instance.get("data") or b"")
        if len(raw) < 4:
            skipped.append(
                {
                    "reason": "too_short",
                    "rule": instance.get("rule"),
                    "identifier": instance.get("identifier"),
                    "offset": instance.get("offset"),
                }
            )
            continue
        pattern = _normalize_pattern(" ".join(f"{byte:02X}" for byte in raw[:64]))
        by_pattern.setdefault(pattern, []).append(instance)

    if not by_pattern:
        return {
            "requested": True,
            "applied": 0,
            "skipped": skipped,
            "resolved": [],
            "writes": [],
        }

    found = _structured_content(
        client.call_tool(
            "find_bytes", {"database": database, "patterns": list(by_pattern), "limit": 2, "offset": 0}
        )
    )
    comments: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    seen_patterns: set[str] = set()
    for result in found.get("result") or []:
        pattern = _normalize_pattern(str(result.get("pattern") or ""))
        seen_patterns.add(pattern)
        matches = list(result.get("matches") or [])
        sources = by_pattern.get(pattern, [])
        if not sources:
            skipped.append({"reason": "unexpected_search_result", "pattern": pattern})
            continue
        if result.get("error"):
            skipped.append({"reason": "search_error", "pattern": pattern, "error": result["error"]})
            continue
        if len(matches) != 1 or int(result.get("n", len(matches))) != 1:
            skipped.append(
                {
                    "reason": "not_unique" if matches else "not_found",
                    "pattern": pattern,
                    "matchCount": int(result.get("n", len(matches))),
                }
            )
            continue
        address = str(matches[0])
        labels = sorted(
            {
                f"{item.get('namespace', 'default')}:{item.get('rule', '')}/{item.get('identifier', '')} file+0x{int(item.get('offset', 0)):X}"
                for item in sources
            }
        )
        comment = "[YARA] " + "; ".join(labels)
        comments.append(
            {"addr": address, "comment": comment, "scope": "line", "dedupe": True}
        )
        results.append({"address": address, "comment": comment})

    for pattern in by_pattern.keys() - seen_patterns:
        skipped.append({"reason": "missing_search_result", "pattern": pattern})

    writes: list[dict[str, Any]] = []
    if comments:
        applied_result = _structured_content(
            client.call_tool("append_comments", {"database": database, "items": comments})
        )
        writes = list(applied_result.get("result") or [])
        failures = [item for item in writes if item.get("error")]
        if failures:
            raise ToolOperationError(f"IDA rejected YARA annotations: {failures}")

    applied = sum(
        bool(item.get("appended", not item.get("skipped")))
        for item in writes
        if not item.get("error")
    )
    return {
        "requested": True,
        "applied": applied,
        "skipped": skipped,
        "resolved": results,
        "writes": writes,
    }
