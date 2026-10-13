import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PRIMARY = "apk-reverse/SKILL.md"


def test_asr_entry_is_discoverable_in_all_routing_surfaces() -> None:
    for name in ("routing.md", "routing_zh.md", "ROUTER.md"):
        text = (ROOT / "skills" / name).read_text(encoding="utf-8")
        assert "asr-registry/" in text
    mirror = json.loads((ROOT / "skills/routing.json").read_text(encoding="utf-8"))
    route = next(row for row in mirror["macro_routes"] if row["id"] == "asr-registry")
    assert route["primary_skill"] == "asr-registry/SKILL.md"
    assert (ROOT / "skills" / route["primary_skill"]).is_file()
    assert {"audited_items_verified", "mcp_servers_excluded"} <= set(route["success_oracles"])


def _matrix_primary(text: str, source: str, target_pattern: str = r"APK\s*/\s*Android(?:\s+.*)?") -> str:
    rows = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if re.fullmatch(target_pattern, cells[0]):
            rows.append(cells)
    assert len(rows) == 1, f"{source}: expected exactly one APK / Android target row"
    assert len(rows[0]) >= 2, f"{source}: missing recommended-entry column"
    entry = re.search(r"`([^`]+)`", rows[0][1])
    assert entry is not None, f"{source}: missing primary skill path"
    path = entry.group(1)
    return path + "SKILL.md" if path.endswith("/") else path


def _assert_apk_contract(documents: dict[str, str]) -> None:
    # Only recommended entries count; alternatives cannot rescue a wrong APK primary.
    for source in ("routing.md", "routing_zh.md"):
        primary = _matrix_primary(documents[source], source)
        assert primary == EXPECTED_PRIMARY, f"{source}: APK / Android primary is {primary}"
    mirror = json.loads(documents["routing.json"])
    routes = [route for route in mirror["macro_routes"] if route["id"] == "apk-android"]
    assert len(routes) == 1, "routing.json: expected exactly one apk-android macro route"
    route = routes[0]
    assert {"apk", "android"} <= set(route["target_kinds"]), "routing.json: missing APK / Android targets"
    assert route["primary_skill"] == EXPECTED_PRIMARY, (
        f"routing.json: APK / Android primary is {route['primary_skill']}"
    )


@pytest.fixture
def aligned_documents() -> dict[str, str]:
    return {
        "routing.md": (
            "| Target Type | Recommended Entry | Alternative |\n"
            "| APK / Android app | `apk-reverse/` — decompile | `mobile-reverse/SKILL.md` |\n"
            "| iOS / IPA app | `mobile-reverse/SKILL.md` | — |\n"
        ),
        "routing_zh.md": (
            "| 目标类型 | 推荐入口 | 备选方案 |\n"
            "| APK / Android 应用 | `apk-reverse/SKILL.md` — 反编译 | `apk-reverse/` — 静态分析 |\n"
            "| iOS / IPA 应用 | `mobile-reverse/SKILL.md` | — |\n"
        ),
        "routing.json": json.dumps({
            "macro_routes": [{
                "id": "apk-android",
                "target_kinds": ["apk", "android", "dex"],
                "primary_skill": "apk-reverse/SKILL.md",
            }],
        }),
    }


def test_apk_android_primary_route_matches_english_chinese_and_json() -> None:
    documents = {
        name: (ROOT / "skills" / name).read_text(encoding="utf-8")
        for name in ("routing.md", "routing_zh.md", "routing.json")
    }
    _assert_apk_contract(documents)

def _assert_firmware_contract(documents: dict[str, str]) -> None:
    for source, target_pattern in (
        ("routing.md", r"Firmware\s*/\s*IoT(?:\s+.*)?"),
        ("routing_zh.md", r"固件\s*/\s*IoT(?:\s+.*)?"),
    ):
        primary = _matrix_primary(documents[source], source, target_pattern)
        assert primary == "firmware-pentest/SKILL.md", (
            f"{source}: firmware / IoT primary is {primary}"
        )
    mirror = json.loads(documents["routing.json"])
    routes = [route for route in mirror["macro_routes"] if route["id"] == "firmware-iot"]
    assert len(routes) == 1, "routing.json: expected exactly one firmware-iot macro route"
    route = routes[0]
    assert {"firmware_image", "router_firmware", "iot_device"} <= set(route["target_kinds"]), (
        "routing.json: missing firmware / IoT targets"
    )
    assert route["primary_skill"] == "firmware-pentest/SKILL.md", (
        f"routing.json: firmware / IoT primary is {route['primary_skill']}"
    )


def test_firmware_route_matches_english_chinese_and_json() -> None:
    documents = {
        name: (ROOT / "skills" / name).read_text(encoding="utf-8")
        for name in ("routing.md", "routing_zh.md", "routing.json")
    }
    _assert_firmware_contract(documents)


def test_firmware_contract_rejects_primary_route_drift(aligned_documents) -> None:
    aligned_documents["routing.md"] += (
        "| Firmware / IoT full-image assessment | `firmware-pentest/SKILL.md` | — |\\n"
    )
    aligned_documents["routing_zh.md"] += (
        "| 固件 / IoT | `firmware-pentest/SKILL.md` | — |\\n"
    )
    mirror = json.loads(aligned_documents["routing.json"])
    mirror["macro_routes"].append({
        "id": "firmware-iot",
        "target_kinds": ["firmware_image", "router_firmware", "iot_device"],
        "primary_skill": "firmware-pentest/SKILL.md",
    })
    aligned_documents["routing.json"] = json.dumps(mirror)
    _assert_firmware_contract(aligned_documents)
    for source in ("routing.md", "routing_zh.md", "routing.json"):
        if source == "routing.json":
            aligned_documents[source] = aligned_documents[source].replace(
                '"firmware-pentest/SKILL.md"', '"reverse-engineering/platforms.md"', 1
            )
        else:
            aligned_documents[source] = aligned_documents[source].replace(
                "`firmware-pentest/SKILL.md`", "`reverse-engineering/platforms.md`", 1
            )
        with pytest.raises(AssertionError, match=re.escape(source)):
            _assert_firmware_contract(aligned_documents)
        aligned_documents[source] = aligned_documents[source].replace(
            '"reverse-engineering/platforms.md"', '"firmware-pentest/SKILL.md"'
        ).replace(
            "`reverse-engineering/platforms.md`", "`firmware-pentest/SKILL.md`"
        )



def test_aligned_primary_routes_allow_other_skills_in_alternatives(aligned_documents) -> None:
    _assert_apk_contract(aligned_documents)


@pytest.mark.parametrize("source", ["routing.md", "routing_zh.md", "routing.json"])
def test_contract_rejects_primary_route_drift(source, aligned_documents) -> None:
    # Plant one primary mismatch; other cells and routes remain unchanged.
    aligned_documents[source] = aligned_documents[source].replace("apk-reverse", "mobile-reverse", 1)
    with pytest.raises(AssertionError, match=re.escape(source)):
        _assert_apk_contract(aligned_documents)


def test_contract_rejects_missing_apk_target_row(aligned_documents) -> None:
    aligned_documents["routing.md"] = "| iOS / IPA app | `mobile-reverse/SKILL.md` | — |\n"
    with pytest.raises(AssertionError, match="routing\\.md: expected exactly one APK / Android target row"):
        _assert_apk_contract(aligned_documents)
