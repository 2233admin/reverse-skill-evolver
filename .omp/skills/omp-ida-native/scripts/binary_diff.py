#!/usr/bin/env python3
"""Compare captured IDA function observations using explicit or unique-name mappings."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


_HEX = re.compile(r"0x[0-9a-fA-F]+\Z")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_AUTO_NAME = re.compile(r"(?:sub_|loc_|FUN_|nullsub_)", re.IGNORECASE)
_SOURCE_FIELDS = ("sha256", "module", "format", "architecture", "bitness", "image_base", "database_id")
_PSEUDOCODE_KINDS = {"pseudocode", "assembly_fallback", "not_collected"}


def compare_snapshots(before: dict, after: dict, mappings: list | None = None) -> dict:
    """Return observed field differences; reject invalid inputs with ValueError.

    Explicit mappings take priority over unique meaningful names. Matching RVAs,
    captured bytes, and pseudocode text do not establish semantic equivalence.
    Inputs are read without mutation; unmatched observations remain unmatched.
    """
    old_source, old_coverage, old_rows = _snapshot(before, "before")
    new_source, new_coverage, new_rows = _snapshot(after, "after")
    for field in ("format", "architecture", "bitness"):
        _require(old_source[field] == new_source[field], f"source {field} differs between snapshots")

    if mappings is None:
        mappings = []
    _require(isinstance(mappings, list), "mapping must be a JSON array")
    used_old: set[int] = set()
    used_new: set[int] = set()
    pairs: list[tuple[dict, dict, str]] = []
    for index, mapping in enumerate(mappings):
        label = f"mapping[{index}]"
        _require(isinstance(mapping, dict) and set(mapping) == {"old_rva", "new_rva"},
                 f"{label} must contain only old_rva and new_rva")
        old_rva = _hex_value(mapping["old_rva"], f"{label}.old_rva")
        new_rva = _hex_value(mapping["new_rva"], f"{label}.new_rva")
        _require(old_rva in old_rows, f"{label}.old_rva is absent from before")
        _require(new_rva in new_rows, f"{label}.new_rva is absent from after")
        _require(old_rva not in used_old, f"{label}.old_rva is duplicated or conflicts with another mapping")
        _require(new_rva not in used_new, f"{label}.new_rva is duplicated or conflicts with another mapping")
        pairs.append((old_rows[old_rva], new_rows[new_rva], "user_mapping"))
        used_old.add(old_rva)
        used_new.add(new_rva)

    old_names = Counter(row["name"] for row in old_rows.values())
    new_names = Counter(row["name"] for row in new_rows.values())
    new_by_name = {row["name"]: row for row in new_rows.values() if new_names[row["name"]] == 1}
    for old_rva, old in old_rows.items():
        name = old["name"]
        if (old_rva in used_old or _AUTO_NAME.match(name)
                or old_names[name] != 1 or new_names[name] != 1):
            continue
        new = new_by_name[name]
        new_rva = int(new["rva"], 16)
        if new_rva in used_new:
            continue
        pairs.append((old, new, "unique_symbol_name"))
        used_old.add(old_rva)
        used_new.add(new_rva)

    truncated = any(
        value is True
        for snapshot in (before, after)
        for record in (snapshot["coverage"], *snapshot["functions"])
        for key, value in record.items()
        if key.endswith("_truncated")
    )
    return {
        "schema_version": 1,
        "sources": {"before": old_source, "after": new_source},
        "coverage": {"before": old_coverage, "after": new_coverage},
        "coverage_truncated": truncated,
        "matches": [_compare_pair(old, new, basis) for old, new, basis in pairs],
        "unmatched_before": [_identity(row) for rva, row in old_rows.items() if rva not in used_old],
        "unmatched_after": [_identity(row) for rva, row in new_rows.items() if rva not in used_new],
        "limitations": [
            "Mappings are explicit selections or unique-name correspondences, not proof of function identity.",
            "Unmatched observations do not establish added or removed functions; truncated coverage is incomplete.",
            "Byte hashes cover the recorded contiguous range; partial hashes never establish whole-function equality.",
            "Pseudocode and callee differences describe captured output, not semantic changes.",
        ],
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _hex_value(value: Any, label: str) -> int:
    _require(isinstance(value, str) and _HEX.fullmatch(value) is not None,
             f"{label} must be a nonnegative 0x-prefixed hexadecimal string")
    return int(value, 16)


def _snapshot(value: Any, label: str) -> tuple[dict, dict, dict[int, dict]]:
    _require(isinstance(value, dict), f"{label} must be an object")
    _require(type(value.get("schema_version")) is int and value["schema_version"] == 1,
             f"{label}.schema_version must be integer 1")
    source = value.get("source")
    _require(isinstance(source, dict), f"{label}.source must be an object")
    for field in _SOURCE_FIELDS:
        _require(field in source, f"{label}.source.{field} is required")
    _require(isinstance(source["sha256"], str) and _SHA256.fullmatch(source["sha256"]) is not None,
             f"{label}.source.sha256 must contain 64 hexadecimal characters")
    for field in ("module", "format", "architecture", "database_id"):
        _require(isinstance(source[field], str) and bool(source[field].strip()),
                 f"{label}.source.{field} must be a nonempty string")
    bits = source["bitness"]
    _require(type(bits) is int and bits in (32, 64), f"{label}.source.bitness must be integer 32 or 64")
    base = _hex_value(source["image_base"], f"{label}.source.image_base")
    _require(base < 1 << bits, f"{label}.source.image_base exceeds bitness")
    coverage = value.get("coverage")
    _require(isinstance(coverage, dict), f"{label}.coverage must be an object")
    _require(all(isinstance(key, str) for key in coverage), f"{label}.coverage field names must be strings")
    total = coverage.get("functions_total")
    _require(type(total) is int and total >= 0, f"{label}.coverage.functions_total must be a nonnegative integer")
    _require(type(coverage.get("functions_truncated")) is bool,
             f"{label}.coverage.functions_truncated must be boolean")
    functions = value.get("functions")
    _require(isinstance(functions, list), f"{label}.functions must be an array")
    _require(total >= len(functions), f"{label}.coverage.functions_total is smaller than the captured list")
    _require(coverage["functions_truncated"] or total == len(functions),
             f"{label}.coverage marks an incomplete function list as complete")
    rows: dict[int, dict] = {}
    for index, row in enumerate(functions):
        prefix = f"{label}.functions[{index}]"
        _require(isinstance(row, dict), f"{prefix} must be an object")
        _require(all(isinstance(key, str) for key in row), f"{prefix} field names must be strings")
        for field in ("ea", "rva", "name", "size", "callees", "bytes_sha256", "bytes_hashed",
                      "bytes_truncated", "pseudocode", "pseudocode_kind"):
            _require(field in row, f"{prefix}.{field} is required")
        rva = _hex_value(row["rva"], f"{prefix}.rva")
        ea = _hex_value(row["ea"], f"{prefix}.ea")
        _require(ea == base + rva and ea < 1 << bits, f"{prefix}.ea must equal image_base + rva within bitness")
        _require(rva not in rows, f"{prefix}.rva duplicates another function")
        _require(isinstance(row["name"], str) and bool(row["name"].strip()), f"{prefix}.name must be nonempty")
        for field in ("size", "bytes_hashed"):
            _require(type(row[field]) is int and row[field] >= 0, f"{prefix}.{field} must be a nonnegative integer")
        _require(row["bytes_hashed"] <= row["size"], f"{prefix}.bytes_hashed exceeds size")
        _require(type(row["bytes_truncated"]) is bool
                 and row["bytes_truncated"] == (row["bytes_hashed"] < row["size"]),
                 f"{prefix}.bytes_truncated must agree with bytes_hashed and size")
        _require(isinstance(row["callees"], list)
                 and all(isinstance(name, str) and name.strip() for name in row["callees"]),
                 f"{prefix}.callees must contain nonempty strings")
        digest = row["bytes_sha256"]
        _require(digest is None or isinstance(digest, str) and _SHA256.fullmatch(digest) is not None,
                 f"{prefix}.bytes_sha256 must be null or a SHA-256 hex string")
        _require(digest is not None or row["bytes_hashed"] == 0,
                 f"{prefix}.bytes_hashed requires bytes_sha256")
        kind = row["pseudocode_kind"]
        _require(isinstance(kind, str) and kind in _PSEUDOCODE_KINDS, f"{prefix}.pseudocode_kind is unsupported")
        _require(row["pseudocode"] is None if kind == "not_collected" else isinstance(row["pseudocode"], str),
                 f"{prefix}.pseudocode must agree with pseudocode_kind")
        rows[rva] = row
        for field, flag in row.items():
            if field.endswith("_truncated"):
                _require(type(flag) is bool, f"{prefix}.{field} must be boolean")
    for field, flag in coverage.items():
        if field.endswith("_truncated"):
            _require(type(flag) is bool, f"{label}.coverage.{field} must be boolean")
    normalized_source = {field: source[field] for field in _SOURCE_FIELDS}
    normalized_source["sha256"] = source["sha256"].lower()
    normalized_source["image_base"] = hex(base)
    return normalized_source, dict(coverage), rows


def _identity(row: dict) -> dict:
    return {"ea": hex(int(row["ea"], 16)), "rva": hex(int(row["rva"], 16)), "name": row["name"], "size": row["size"]}


def _observation(row: dict) -> dict:
    digest = row["bytes_sha256"]
    text = row["pseudocode"]
    return {
        **_identity(row),
        "callees": sorted(set(row["callees"])),
        "callees_truncated": row.get("callees_truncated"),
        "bytes": {
            "sha256": digest.lower() if digest is not None else None,
            "hashed": row["bytes_hashed"],
            "truncated": row["bytes_truncated"],
            "complete_range": digest is not None and row["bytes_hashed"] == row["size"] and not row["bytes_truncated"],
        },
        "pseudocode": {
            "kind": row["pseudocode_kind"],
            "available": row["pseudocode_kind"] == "pseudocode" and text is not None,
            "truncated": row.get("pseudocode_truncated"),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None,
        },
    }


def _compare_pair(old: dict, new: dict, basis: str) -> dict:
    before, after = _observation(old), _observation(new)
    complete = before["bytes"]["complete_range"] and after["bytes"]["complete_range"]
    if complete:
        byte_comparison = ("complete_range_hash_equal" if before["bytes"]["sha256"] == after["bytes"]["sha256"]
                           else "complete_range_hash_different")
    else:
        byte_comparison = "partial_or_missing_bytes"
    return {
        "mapping_basis": basis,
        "before": before,
        "after": after,
        "changed_fields": [field for field in ("rva", "name", "size", "callees", "callees_truncated", "bytes", "pseudocode")
                           if before[field] != after[field]],
        "byte_comparison": byte_comparison,
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare captured IDA function observations.")
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--mapping", type=Path, help="JSON array of old_rva/new_rva mappings")
    parser.add_argument("--output", type=Path, help="create a new JSON file; existing files are refused")
    args = parser.parse_args(argv)
    try:
        if args.output:
            inputs = [args.before, args.after] + ([args.mapping] if args.mapping else [])
            _require(args.output.resolve() not in [path.resolve() for path in inputs],
                     "output must not be an input or mapping path")
        report = compare_snapshots(_load(args.before), _load(args.after),
                                   _load(args.mapping) if args.mapping else None)
        payload = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        if args.output:
            with args.output.open("xb") as output:
                output.write(payload)
        else:
            sys.stdout.write(payload.decode("utf-8"))
    except (OSError, ValueError) as error:
        print(f"binary-diff: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
