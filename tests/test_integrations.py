from pathlib import Path

import pytest

from reverse_skill.errors import ToolOperationError
from reverse_skill.integrations import annotate_yara_matches, scan_yara


class FakeClient:
    def __init__(self, target: Path) -> None:
        self.target = target
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name: str, arguments: dict | None = None, **_: object) -> dict:
        payload = arguments or {}
        self.calls.append((name, payload))
        if name == "server_health":
            return {"input_path": str(self.target)}
        if name == "find_bytes":
            patterns = payload["patterns"]
            return {
                "result": [
                    {"pattern": patterns[0].lower(), "matches": ["0x140001000"], "n": 1},
                    {"pattern": patterns[1], "matches": ["0x1", "0x2"], "n": 2},
                ]
            }
        if name == "append_comments":
            return {
                "result": [
                    {"addr": item["addr"], "appended": True, "skipped": False}
                    for item in payload["items"]
                ]
            }
        raise AssertionError(name)


def test_yara_scan_returns_offsets_and_matched_bytes(tmp_path: Path) -> None:
    pytest.importorskip("yara")
    target = tmp_path / "sample.bin"
    target.write_bytes(b"prefix-unique-marker-suffix")
    rules = tmp_path / "sample.yar"
    rules.write_text(
        'rule marker { strings: $marker = "unique-marker" condition: $marker }',
        encoding="utf-8",
    )

    result, inputs = scan_yara(target, [rules], timeout=5)

    assert result["summary"] == {"ruleMatches": 1, "stringMatches": 1, "instanceMatches": 1}
    assert inputs[0]["offset"] == 7
    assert inputs[0]["data"] == b"unique-marker"


def test_annotation_only_writes_unique_byte_matches(tmp_path: Path) -> None:
    target = tmp_path / "sample.bin"
    target.write_bytes(b"unused")
    client = FakeClient(target)
    instances = [
        {"namespace": "rules_0", "rule": "one", "identifier": "$a", "offset": 1, "data": b"unique"},
        {"namespace": "rules_0", "rule": "two", "identifier": "$b", "offset": 2, "data": b"repeat"},
        {"namespace": "rules_0", "rule": "tiny", "identifier": "$c", "offset": 3, "data": b"abc"},
    ]

    result = annotate_yara_matches(client, "session", target, instances)

    assert result["applied"] == 1
    assert {item["reason"] for item in result["skipped"]} == {"not_unique", "too_short"}
    assert result["writes"][0]["appended"] is True
    append = next(payload for name, payload in client.calls if name == "append_comments")
    assert append["items"][0]["addr"] == "0x140001000"
    assert "rules_0:one/$a" in append["items"][0]["comment"]


def test_annotation_rejects_a_different_open_database(tmp_path: Path) -> None:
    target = tmp_path / "sample.bin"
    target.write_bytes(b"unused")
    other = tmp_path / "other.bin"
    other.write_bytes(b"unused")
    client = FakeClient(other)

    with pytest.raises(ToolOperationError, match="different IDA database"):
        annotate_yara_matches(client, "session", target, [])

    assert [name for name, _ in client.calls] == ["server_health"]
