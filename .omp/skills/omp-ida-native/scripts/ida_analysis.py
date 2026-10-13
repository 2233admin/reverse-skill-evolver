"""Read-only evidence collection in an existing OMP native IDA exec namespace."""

import hashlib
import re


def _limit(value, name, maximum, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def _source(namespace, database_id):
    if not isinstance(database_id, str) or not database_id.strip():
        raise ValueError("database_id must be the explicit native database ID")
    db = namespace["db"]
    digest = str(db.sha256).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("db.sha256 must identify the input with a SHA-256 digest")
    if isinstance(db.bitness, bool) or not isinstance(db.bitness, int) or db.bitness not in (32, 64):
        raise ValueError("db.bitness must be 32 or 64")
    base = db.base_address
    if isinstance(base, bool) or not isinstance(base, int) or not 0 <= base < 1 << db.bitness:
        raise ValueError("db.base_address is outside the input address space")
    return {
        "sha256": digest,
        "module": str(db.module),
        "format": str(db.format),
        "architecture": str(db.architecture),
        "bitness": db.bitness,
        "image_base": hex(base),
        "database_id": database_id,
    }


def _location(ea, source):
    base = int(source["image_base"], 16)
    if isinstance(ea, bool) or not isinstance(ea, int) or not base <= ea < 1 << source["bitness"]:
        raise ValueError(f"address {ea!r} is outside the input image address space")
    return {"ea": hex(ea), "rva": hex(ea - base)}


def collect_snapshot(
    namespace, database_id, *, max_functions=500, max_strings=200, max_imports=200,
    max_callees=25, max_bytes_per_function=256, collect_pseudocode=False,
    max_pseudocode_functions=10, max_pseudocode_chars=8000, max_text_chars=4096,
):
    """Return bounded JSON data; native enumeration itself scans the complete database."""
    limits = {
        "max_functions": _limit(max_functions, "max_functions", 5000),
        "max_strings": _limit(max_strings, "max_strings", 5000),
        "max_imports": _limit(max_imports, "max_imports", 5000),
        "max_callees": _limit(max_callees, "max_callees", 500),
        "max_bytes_per_function": _limit(max_bytes_per_function, "max_bytes_per_function", 4096),
        "max_pseudocode_functions": _limit(max_pseudocode_functions, "max_pseudocode_functions", 50),
        "max_pseudocode_chars": _limit(max_pseudocode_chars, "max_pseudocode_chars", 20000, 1),
        "max_text_chars": _limit(max_text_chars, "max_text_chars", 16384, 1),
    }
    if not isinstance(collect_pseudocode, bool):
        raise ValueError("collect_pseudocode must be a boolean")
    source = _source(namespace, database_id)
    all_functions = namespace["functions"]()
    all_strings = namespace["strings"]()
    all_imports = namespace["imports"]()
    coverage = {
        "native_enumeration": "full_helper_scan",
        "functions_total": len(all_functions),
        "functions_truncated": len(all_functions) > max_functions,
        "strings_total": len(all_strings),
        "strings_truncated": len(all_strings) > max_strings,
        "imports_total": len(all_imports),
        "imports_truncated": len(all_imports) > max_imports,
        "callees_truncated": False,
        "bytes_truncated": False,
        "strings_text_truncated": False,
        "pseudocode_requested": collect_pseudocode,
        "pseudocode_functions_collected": 0,
        "pseudocode_functions_truncated": collect_pseudocode and min(len(all_functions), max_functions) > max_pseudocode_functions,
        "pseudocode_text_truncated": False,
        "limits": limits,
    }
    rows = []
    for index, (ea, name) in enumerate(all_functions[:max_functions]):
        function = namespace["func"](ea)
        size = function.size()
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"invalid function size at {hex(ea)}")
        callees = namespace["callees"](ea)
        wanted = min(size, max_bytes_per_function)
        raw = (namespace["ida_bytes"].get_bytes(ea, wanted) or b"") if wanted else b""
        if not isinstance(raw, bytes) or len(raw) > wanted:
            raise ValueError(f"unexpected raw byte result at {hex(ea)}")
        row = {
            **_location(ea, source), "name": name, "size": size,
            "callees": callees[:max_callees], "callees_truncated": len(callees) > max_callees,
            "bytes_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
            "bytes_hashed": len(raw), "bytes_truncated": len(raw) < size,
            "bytes_start_ea": hex(ea), "bytes_end_ea": hex(ea + len(raw)),
            "pseudocode": None, "pseudocode_kind": "not_collected",
            "pseudocode_truncated": False,
        }
        if collect_pseudocode and index < max_pseudocode_functions:
            text = namespace["pseudocode"](ea)
            fallback = text.startswith("// decompilation failed:", text.find("\n") + 1)
            row.update(
                pseudocode=text[:max_pseudocode_chars],
                pseudocode_kind="assembly_fallback" if fallback else "pseudocode",
                pseudocode_truncated=len(text) > max_pseudocode_chars,
            )
            coverage["pseudocode_functions_collected"] += 1
        coverage["callees_truncated"] |= row["callees_truncated"]
        coverage["bytes_truncated"] |= row["bytes_truncated"]
        coverage["pseudocode_text_truncated"] |= row["pseudocode_truncated"]
        rows.append(row)
    strings = []
    for ea, value in all_strings[:max_strings]:
        truncated = len(value) > max_text_chars
        strings.append({"ea": hex(ea), "value": value[:max_text_chars], "value_truncated": truncated})
        coverage["strings_text_truncated"] |= truncated
    imports = [{"ea": hex(ea), "module": module or "", "name": name} for ea, module, name in all_imports[:max_imports]]
    return {"schema_version": 1, "source": source, "coverage": coverage, "functions": rows, "strings": strings, "imports": imports}


def _matches(rows, pattern, value_of, max_matches, max_scan, max_chars):
    matches, scanned, text_truncated = [], 0, False
    for row in rows:
        if scanned >= max_scan or len(matches) >= max_matches:
            break
        value = value_of(row)
        text_truncated |= len(value) > max_chars
        scanned += 1
        if pattern.search(value[:max_chars]):
            matches.append(row)
    return matches, {
        "total": len(rows), "scanned": scanned, "scan_truncated": scanned < len(rows),
        "matches": len(matches), "text_truncated": text_truncated,
    }


def triage(
    namespace, database_id, *,
    function_pattern=r"parse|decode|decrypt|auth|login|check|verify|password|token|key|exec|system|shell|memcpy|strcpy",
    string_pattern=r"password|token|secret|license|invalid|unauthorized|https?://",
    import_pattern=r"memcpy|strcpy|sprintf|system|exec|crypt|socket|connect|recv|send|read|write",
    max_candidates=50, max_matches_per_source=100, max_xref_queries=100,
    max_xrefs_per_source=100, max_evidence_per_candidate=20,
    max_scan_per_source=10000, max_subject_chars=4096,
):
    """Rank bounded name/string/import leads; scores are not vulnerability judgments."""
    limits = {
        "max_candidates": _limit(max_candidates, "max_candidates", 50, 1),
        "max_matches_per_source": _limit(max_matches_per_source, "max_matches_per_source", 100),
        "max_xref_queries": _limit(max_xref_queries, "max_xref_queries", 100),
        "max_xrefs_per_source": _limit(max_xrefs_per_source, "max_xrefs_per_source", 1000),
        "max_evidence_per_candidate": _limit(max_evidence_per_candidate, "max_evidence_per_candidate", 100, 1),
        "max_scan_per_source": _limit(max_scan_per_source, "max_scan_per_source", 100000),
        "max_subject_chars": _limit(max_subject_chars, "max_subject_chars", 16384, 1),
        "max_pattern_chars": 256,
    }
    patterns = []
    for pattern in (function_pattern, string_pattern, import_pattern):
        if not isinstance(pattern, str) or not 1 <= len(pattern) <= limits["max_pattern_chars"]:
            raise ValueError("each regex must contain between 1 and 256 characters")
        patterns.append(re.compile(pattern, re.IGNORECASE))
    source = _source(namespace, database_id)
    functions, function_scan = _matches(namespace["functions"](), patterns[0], lambda row: row[1], max_matches_per_source, max_scan_per_source, max_subject_chars)
    strings, string_scan = _matches(namespace["strings"](), patterns[1], lambda row: row[1], max_matches_per_source, max_scan_per_source, max_subject_chars)
    imports, import_scan = _matches(namespace["imports"](), patterns[2], lambda row: f"{row[1] or ''}!{row[2]}", max_matches_per_source, max_scan_per_source, max_subject_chars)
    coverage = {
        "native_enumeration": "full_helper_scan",
        "functions_total": function_scan["total"],
        "functions_truncated": function_scan["scan_truncated"],
        "strings_truncated": string_scan["scan_truncated"],
        "imports_truncated": import_scan["scan_truncated"],
        "source_scans": {"functions": function_scan, "strings": string_scan, "imports": import_scan},
        "xref_queries": 0, "xref_rows_total": 0, "xref_rows_truncated": False,
        "non_function_xrefs_skipped": 0, "evidence_truncated": False,
        "patterns": {"functions": function_pattern, "strings": string_pattern, "imports": import_pattern},
        "limits": limits,
    }
    candidates = {}

    def add(ea, name, evidence, weight):
        candidate = candidates.setdefault(ea, {
            **_location(ea, source), "name": name, "score": 0, "evidence": [],
            "next_action": "Inspect this function's pseudocode or assembly and verify the cited xref sites.",
            "_seen": set(),
        })
        key = (evidence["kind"], evidence["source_ea"], evidence.get("xref_from"))
        if key in candidate["_seen"]:
            return
        candidate["_seen"].add(key)
        candidate["score"] += weight
        if len(candidate["evidence"]) < max_evidence_per_candidate:
            candidate["evidence"].append(evidence)
        else:
            coverage["evidence_truncated"] = True

    for ea, name in functions:
        add(ea, name, {"kind": "function_name", "source_ea": hex(ea), "value": name}, 3)
    targets = []
    # Interleave sources so string matches cannot consume every import query.
    for index in range(max(len(strings), len(imports))):
        if index < len(strings):
            ea, value = strings[index]
            targets.append(("string", ea, value))
        if index < len(imports):
            ea, module, name = imports[index]
            targets.append(("import", ea, f"{module or ''}!{name}"))
    coverage["xref_queries_truncated"] = len(targets) > max_xref_queries
    for kind, ea, value in targets[:max_xref_queries]:
        xrefs = namespace["xrefs_to"](ea)
        coverage["xref_queries"] += 1
        coverage["xref_rows_total"] += len(xrefs)
        coverage["xref_rows_truncated"] |= len(xrefs) > max_xrefs_per_source
        for xref in xrefs[:max_xrefs_per_source]:
            site = xref["from"]
            if xref["func"] is None:
                coverage["non_function_xrefs_skipped"] += 1
                continue
            try:
                owner = namespace["func"](site).start_ea
            except LookupError as error:
                if str(error) != f"no function at {hex(site)}":
                    raise
                coverage["non_function_xrefs_skipped"] += 1
                continue
            add(owner, xref["func"], {
                "kind": kind, "source_ea": hex(ea), "value": value[:max_subject_chars],
                "value_truncated": len(value) > max_subject_chars,
                "xref_from": hex(site), "xref_type": xref["type"],
            }, 2)
    ranked = sorted(candidates.values(), key=lambda row: (-row["score"], int(row["ea"], 16)))
    coverage["candidates_total"] = len(ranked)
    coverage["candidates_truncated"] = len(ranked) > max_candidates
    for row in ranked[:max_candidates]:
        del row["_seen"]
    return {"schema_version": 1, "source": source, "coverage": coverage, "candidates": ranked[:max_candidates]}
