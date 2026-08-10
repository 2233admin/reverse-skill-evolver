from pathlib import Path

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
