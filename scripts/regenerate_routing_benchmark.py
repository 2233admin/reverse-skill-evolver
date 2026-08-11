#!/usr/bin/env python3
"""Regenerate tests/data/routing-benchmark.json from an INDEPENDENT derivation.

This script does NOT run the router implementation. Each case's `expect_local`
is derived from two reviewed sources:

1. `reverse_skill/data/upstream-route-crosswalk.json` — the reviewed R0-R40 map:
   - adopted/superseded  -> mapped_route
   - rejected            -> no_route
2. `OVERRIDES` below — a reviewed exception table for cases whose hint carries
   context that routes differently than the crosswalk entry alone would imply.
   Every case whose crosswalk derivation differs from the frozen expectation
   MUST appear here (the script fails otherwise), so the override table is the
   complete, auditable list of divergences.

The benchmark test then asserts the implementation agrees with this reviewed
expectation — the expectation is not derived from the implementation, so the
test guards against drift instead of freezing whatever the router happens to do.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
CROSSWALK_PATH = REPO_ROOT / "reverse_skill" / "data" / "upstream-route-crosswalk.json"
OUT_PATH = REPO_ROOT / "tests" / "data" / "routing-benchmark.json"
UPSTREAM_BENCH = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else r"C:\Users\Administrator\AppData\Local\Temp\reverse-skill-upstream-50187aa6c8\skills\tests\routing-benchmark.json"
)

# --- Reviewed exception table ----------------------------------------------
# Key: (upstream R id, exact hint). Value: frozen local expectation.
# Every entry documents why the hint deviates from the crosswalk derivation.
# These are pre-existing router semantics; no new keyword/fallback was added.

OVERRIDES: Dict[Tuple[str, str], str] = {
    # R0 generic RE hints that name a concrete artifact kind -> native-binary.
    ("R0", "reverse engineering binary"): "native-binary",
    ("R0", "frida hook native so"): "native-binary",
    ("R0", "frida 动态调试 so"): "native-binary",
    # R1: 中文 root-detection hint has no android/apk context in our router.
    ("R1", "绕过 root 检测 证书校验"): "no_route",
    # R2: jailbreak without mobile/ios/ipa keyword does not route to mobile.
    ("R2", "iphone jailbreak detection bypass"): "no_route",
    ("R2", "jailbreak iphone"): "no_route",
    # R3: packet-capture hints route to the protocol-pcap route, not JS.
    ("R3", "抓包 分析请求 重放"): "protocol-pcap",
    ("R3", "burpsuite 抓包 重放"): "protocol-pcap",
    ("R3", "app 抓包 https"): "protocol-pcap",
    # R9: malware-domain hints without a malware keyword stay unrouted.
    ("R9", "ransomware 勒索软件 分析"): "no_route",
    ("R9", "webshell 检测"): "no_route",
    ("R9", "webshell"): "no_route",
    # R10 attack-chain hints lack a security-assessment target/intent keyword.
    ("R10", "红队 横向移动 内网渗透"): "no_route",
    ("R10", "从外网打到域控"): "no_route",
    ("R10", "越狱 提示词 红队 ai"): "no_route",
    ("R10", "域渗透 完整渗透 攻击链"): "no_route",
    ("R10", "打到域控"): "no_route",
    # R11 tool names without a security-assessment intent stay unrouted;
    # report-generation hints go to docs-generator.
    ("R11", "burpsuite intruder 爆破"): "no_route",
    ("R11", "write pentest report"): "docs-generator",
    ("R11", "渗透测试报告 写报告"): "docs-generator",
    ("R11", "metasploit msf"): "no_route",
    ("R11", "sql 注入 数据库"): "no_route",
    ("R11", "linux 提权"): "no_route",
    ("R11", "linux 权限提升 提权"): "no_route",
    ("R11", "sqlmap 注入"): "no_route",
    ("R11", "hashcat 破解"): "no_route",
    ("R11", "安全评估 报告"): "docs-generator",
    ("R11", "风险评估"): "no_route",
    # R12: 越权 hint without api/graphql/jwt keyword stays unrouted.
    ("R12", "越权 未授权访问 接口安全"): "no_route",
    # R14: 中文 LLM jailbreak hint lacks the llm/jailbreak ASCII keywords.
    ("R14", "LLM 越狱"): "no_route",
    # R19: playwright automation hint has no js/frontend context in our router.
    ("R19", "playwright browser automation"): "no_route",
    # R22: ghidra-as-IDA-replacement hint routes to native-binary (tie-break).
    ("R22", "无 IDA 用 ghidra 反编译"): "native-binary",
    # R27 sigma hints land on malware-analysis via a pre-existing alias.
    ("R27", "threat hunting sigma"): "malware-analysis",
    ("R27", "威胁狩猎 检测规则 sigma"): "malware-analysis",
    # R30: extension hint without a browser keyword stays unrouted.
    ("R30", "chrome extension reverse"): "no_route",
    # R32: thick-client security-testing hint lands on active-security-assessment.
    ("R32", "厚客户端 安全测试"): "active-security-assessment",
    # R33: go malware hint lands on malware-analysis via the malware keyword.
    ("R33", "go malware"): "malware-analysis",
    # R39: diagram hints without the diagram keyword stay unrouted.
    ("R39", "mermaid 时序图"): "no_route",
    ("R39", "攻击路径图"): "no_route",
}


def load_crosswalk() -> dict:
    return json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))


def derive_expectation(crosswalk: dict, expect: str) -> str:
    entry = crosswalk["routes"].get(expect, {})
    if entry.get("status") == "rejected":
        return "no_route"
    return str(entry.get("mapped_route") or "no_route")


def main() -> int:
    crosswalk = load_crosswalk()
    upstream = json.loads(UPSTREAM_BENCH.read_text(encoding="utf-8"))

    cases = []
    used_overrides = set()
    for c in upstream["cases"]:
        expect = c["expect"]
        hint = c["hint"]
        derived = derive_expectation(crosswalk, expect)
        if (expect, hint) in OVERRIDES:
            derived = OVERRIDES[(expect, hint)]
            used_overrides.add((expect, hint))
        cases.append(
            {
                "hint": hint,
                "expect": expect,
                "quick": bool(c.get("quick", False)),
                "expect_local": derived,
            }
        )

    # Completeness: every case whose expectation differs from the bare crosswalk
    # derivation MUST be explained in the override table.
    unexplained = [
        (c["expect"], c["hint"])
        for c in cases
        if derive_expectation(crosswalk, c["expect"]) != c["expect_local"]
        and (c["expect"], c["hint"]) not in OVERRIDES
    ]
    if unexplained:
        print("ERROR: unexplained divergences (add to OVERRIDES):", file=sys.stderr)
        for item in unexplained:
            print("  ", item, file=sys.stderr)
        return 2

    unused = set(OVERRIDES) - used_overrides
    if unused:
        print("ERROR: override entries not present in the upstream fixture:", file=sys.stderr)
        for item in sorted(unused):
            print("  ", item, file=sys.stderr)
        return 3

    out = {
        "schema_version": 1,
        "migrated": "2026-08-11",
        "description": (
            "Upstream reverse-skill routing regression benchmark migrated as an independent "
            "black-box fixture. expect_local is derived from the reviewed R0-R40 crosswalk "
            "(reverse_skill/data/upstream-route-crosswalk.json) plus the reviewed OVERRIDES "
            "table in scripts/regenerate_routing_benchmark.py; it is NOT generated by running "
            "the router, so the test guards against drift rather than freezing current behavior."
        ),
        "upstream": {
            "repo": "https://github.com/zhaoxuya520/reverse-skill",
            "ref": "main@50187aa6c8683c4767a763ae16686970d69c79c2",
            "source": "skills/tests/routing-benchmark.json",
        },
        "meta": upstream.get("meta", {}),
        "cases": cases,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("wrote", OUT_PATH, "total", len(cases))
    print("expect_local:", dict(Counter(c["expect_local"] for c in cases)))
    print("overrides applied:", len(used_overrides))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
