from pathlib import Path

import pytest

from reverse_skill.ida import find_latest_ida, format_version, parse_version


def _fake_ida(parent: Path, name: str) -> Path:
    install = parent / name
    install.mkdir()
    (install / "ida.exe").touch()
    (install / "idalib.dll").touch()
    return install


def test_parse_and_format_version() -> None:
    assert parse_version("IDA Professional 9.4.260714.951") == (9, 4, 260714, 951)
    assert parse_version("not a version") == (0, 0, 0, 0)
    assert format_version((9, 4, 0, 0)) == "9.4"


def test_find_latest_ida_uses_highest_valid_candidate(tmp_path: Path) -> None:
    ida_92 = _fake_ida(tmp_path, "IDA Professional 9.2")
    ida_94 = _fake_ida(tmp_path, "IDA Professional 9.4")
    invalid = tmp_path / "IDA Professional 9.9"
    invalid.mkdir()
    (invalid / "ida.exe").touch()

    latest = find_latest_ida([ida_92, invalid, ida_94], only_candidates=True)

    assert latest is not None
    assert Path(latest.install_dir) == ida_94.resolve()
    assert latest.version == "9.4"
    assert latest.public()["installDir"] == str(ida_94.resolve())
    assert "version_key" not in latest.public()


def test_find_latest_ida_returns_none_without_idalib(tmp_path: Path) -> None:
    invalid = tmp_path / "IDA Professional 10.0"
    invalid.mkdir()
    (invalid / "ida.exe").touch()

    assert find_latest_ida([invalid], only_candidates=True) is None


def test_start_server_readiness_probes_share_one_deadline(monkeypatch) -> None:
    from reverse_skill import ida

    clock = [0.0]
    probe_deadlines = []

    class FakeInstallation:
        install_dir = "C:/IDA"

        def public(self):
            return {"installDir": self.install_dir}

    monkeypatch.setattr(ida, "find_latest_ida", lambda *_args, **_kwargs: FakeInstallation())
    monkeypatch.setattr(ida, "find_server_executable", lambda _path: "idalib-mcp")
    monkeypatch.setattr(ida.subprocess, "Popen", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(ida.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ida.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    def probe(_port: int, deadline: float) -> int:
        probe_deadlines.append(deadline)
        clock[0] += min(3.0, max(0.0, deadline - clock[0]))
        return 0

    try:
        ida.start_server(probe=probe, wait_seconds=15)
    except ida.McpTransportError:
        pass
    else:
        raise AssertionError("unready server should time out")

    assert clock[0] <= 15
    assert probe_deadlines[0] == 15
    assert all(deadline == 15 for deadline in probe_deadlines)


@pytest.mark.parametrize("late_on_first_probe", [True, False])
def test_start_server_rejects_late_positive_probe(monkeypatch, late_on_first_probe: bool) -> None:
    from reverse_skill import ida

    clock = [0.0]
    calls = [0]

    class FakeInstallation:
        install_dir = "C:/IDA"

        def public(self):
            return {"installDir": self.install_dir}

    monkeypatch.setattr(ida, "find_latest_ida", lambda *_args, **_kwargs: FakeInstallation())
    monkeypatch.setattr(ida, "find_server_executable", lambda _path: "idalib-mcp")
    monkeypatch.setattr(ida.subprocess, "Popen", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(ida.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ida.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    def probe(_port: int, deadline: float) -> int:
        calls[0] += 1
        if late_on_first_probe or calls[0] > 1:
            clock[0] = deadline
            return 1
        return 0

    with pytest.raises(ida.McpTransportError, match="did not become ready"):
        ida.start_server(probe=probe, wait_seconds=3)
