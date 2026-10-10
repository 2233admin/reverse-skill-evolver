from collections import Counter
from pathlib import Path
from unittest.mock import Mock

import pytest

from reverse_skill.errors import ToolOperationError
from reverse_skill.integrations import annotate_yara_matches, integration_inventory, scan_yara


@pytest.mark.parametrize(
    ("executables", "modules", "expected"),
    [
        (
            {"capa", "floss", "r2", "rabin2", "bindiff", "diaphora", "x64dbg", "x96dbg", "windbg", "cdb"},
            {"yara", "capa", "floss", "diaphora"},
            (
                (True, "python:yara"), (True, "/tools/capa"), (True, "/tools/floss"),
                (True, "/tools/rabin2"), (True, "/tools/bindiff"), (True, "/tools/diaphora"),
                (True, "/tools/x64dbg"), (True, "/tools/windbg"),
            ),
        ),
        (
            {"rabin2", "x96dbg", "cdb"},
            {"capa", "floss", "diaphora"},
            (
                (False, None), (True, "python:capa"), (True, "python:floss"),
                (False, "/tools/rabin2"), (False, None), (True, "python:diaphora"),
                (True, "/tools/x96dbg"), (True, "/tools/cdb"),
            ),
        ),
        (
            set(),
            {"yara", "capa", "floss", "diaphora"},
            (
                (True, "python:yara"), (True, "python:capa"), (True, "python:floss"),
                (False, None), (False, None), (True, "python:diaphora"),
                (False, None), (False, None),
            ),
        ),
        (
            {"r2"},
            set(),
            (
                (False, None), (False, None), (False, None), (False, "/tools/r2"),
                (False, None), (False, None), (False, None), (False, None),
            ),
        ),
        (set(), set(), ((False, None),) * 8),
    ],
    ids=["primary-executables", "fallbacks-and-rabin2-only", "python-only", "r2-only", "missing"],
)
def test_inventory_reuses_discovery_only_within_each_invocation(
    monkeypatch: pytest.MonkeyPatch,
    executables: set[str],
    modules: set[str],
    expected: tuple[tuple[bool, str | None], ...],
) -> None:
    executables = executables.copy()
    modules = modules.copy()
    which = Mock(side_effect=lambda name: f"/tools/{name}" if name in executables else None)
    find_spec = Mock(side_effect=lambda name: object() if name in modules else None)
    monkeypatch.setattr("reverse_skill.integrations.shutil.which", which)
    monkeypatch.setattr("reverse_skill.integrations.importlib.util.find_spec", find_spec)
    monkeypatch.setattr("reverse_skill.integrations.importlib.metadata.version", lambda name: "1.2.3")

    for want in (expected, ((False, None),) * 8):
        values = integration_inventory()

        assert [item["name"] for item in values] == [
            "yara", "capa", "floss", "radare2", "bindiff", "diaphora", "x64dbg", "windbg",
        ]
        assert tuple((item["available"], item["entry"]) for item in values) == want
        assert all(
            set(item) == {"name", "available", "version", "entry", "support", "idaBridge"}
            for item in values
        )
        assert values[0]["support"] == "ready"
        assert values[0]["idaBridge"] == ["scan", "annotate-unique-byte-matches"]
        assert all(item["support"] == "discovery_only" and item["idaBridge"] == [] for item in values[1:])
        assert [item["version"] for item in values] == [
            "1.2.3" if want[0][0] else None, "1.2.3", "1.2.3", None,
            None, "1.2.3", None, None,
        ]
        for discovery in (which, find_spec):
            counts = Counter(call.args[0] for call in discovery.call_args_list)
            assert all(count == 1 for count in counts.values())
            discovery.reset_mock()
        executables.clear()
        modules.clear()


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
