"""Deterministic skill selection; no tool execution or environment changes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PACK_ROOT = Path(__file__).resolve().parent.parent
ROUTING_PATH = PACK_ROOT / "skills" / "routing.json"
if not ROUTING_PATH.is_file():
    ROUTING_PATH = Path(__file__).resolve().parent / "data" / "routing.json"


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def contains_keyword(text: str, keyword: str) -> bool:
    needle, text = normalize(keyword), normalize(text)
    if not needle:
        return False
    if re.fullmatch(r"[a-z0-9_ .+/-]+", needle):
        return re.search(rf"(?<![a-z0-9_]){re.escape(needle)}(?![a-z0-9_])", text) is not None
    compact_needle = re.sub(r"[^\w\u0080-\uffff]+", "", needle)
    compact_text = re.sub(r"[^\w\u0080-\uffff]+", "", text)
    return needle in text or compact_needle in compact_text


def _task_text(task: dict[str, Any]) -> str:
    return " ".join(str(task.get(key) or "") for key in
                    ("task", "intent", "target_kind", "mode", "toolchain", "evidence", "input_path"))


def _target_kind(task: dict[str, Any], data: dict[str, Any]) -> str:
    explicit = normalize(task.get("target_kind"))
    for route_id, aliases in data.get("target_aliases", {}).items():
        if explicit and (explicit == route_id or explicit in {normalize(a) for a in aliases}):
            return route_id
    if explicit:
        return explicit
    text = _task_text(task)
    if any(contains_keyword(text, alias) for alias in ("forefy", "asr")):
        return "asr-registry"
    suffix = Path(str(task.get("input_path") or "")).suffix.casefold()
    for route_id, suffixes in {
        "apk-android": (".apk", ".xapk", ".dex", ".smali"),
        "js-browser-signature": (".js", ".mjs", ".cjs", ".map"),
        "native-binary": (".exe", ".dll", ".sys", ".elf", ".so", ".dylib", ".macho"),
        "protocol-pcap": (".pcap", ".pcapng"),
        "protocol-source-implementation": (".rs", ".toml"),
    }.items():
        if suffix in suffixes:
            return route_id
    for route_id, aliases in data.get("route_aliases", {}).items():
        if any(contains_keyword(text, alias) for alias in aliases):
            return route_id
    return ""


def build_plan(task: dict[str, Any]) -> dict[str, Any]:
    """Select a bundled workflow. Availability and authorization remain unverified."""
    data = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    target = _target_kind(task, data)
    text = _task_text(task)
    explicit = normalize(task.get("route_id"))
    scored = []
    for route in data["macro_routes"]:
        route_id = route["id"]
        if explicit and explicit != route_id:
            continue
        score, signals = (10000, ["explicit_route_id"]) if explicit else (0, [])
        if target == route_id or target in route.get("target_kinds", []):
            score += 100
            signals.append("target_kind:" + target)
        aliases = [a for a in data.get("route_aliases", {}).get(route_id, []) if contains_keyword(text, a)]
        score += min(60, len(aliases) * 12)
        signals.extend("alias:" + a for a in aliases[:5])
        for keyword in route.get("intent_keywords", []):
            if contains_keyword(text, keyword):
                score += 10
                signals.append("keyword:" + keyword)
        scored.append((score, route, signals))
    scored.sort(key=lambda item: (target == "asr-registry" and item[1]["id"] == "asr-registry", item[0]), reverse=True)
    if not scored or scored[0][0] <= 0:
        return {"schema_version": 1, "status": "no_route", "target_kind": target,
                "reason": "no_target_or_intent_match", "executed": False}
    score, route, signals = scored[0]
    return {"schema_version": 1, "status": "selected", "target_kind": target,
            "route": {"id": route["id"], "base_id": route["id"], "skill": route["primary_skill"]},
            "score": score, "signals": signals, "executed": False,
            "requires_capabilities": route.get("requires_capabilities", []),
            "requires_any_capabilities": route.get("requires_any_capabilities", []),
            "fallback_edges": route.get("fallback_edges", []),
            "success_oracles": route.get("success_oracles", []),
            "preflight": {"status": "not_run", "authorization_verified": False,
                          "capabilities_verified": False}}
