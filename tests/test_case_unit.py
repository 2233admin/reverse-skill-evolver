"""Author-side unit tests for the frozen case contracts and parser internals."""

import hashlib
import json
from pathlib import Path

import pytest

from reverse_skill.case import (
    CaseContractError,
    CasePackageError,
    init_case,
    normalize_hash,
    normalize_network_profile,
    resolve_artifact,
    review_case,
    sha256_file,
    slugify,
    validate_case_name,
    parse_scope,
)

ROOT = Path(__file__).resolve().parents[1]


def test_contracts_file_is_valid_and_frozen() -> None:
    contracts = json.loads(
        (ROOT / "reverse_skill" / "data" / "case-contracts.json").read_text(encoding="utf-8")
    )
    assert contracts["schema_version"] == 1
    assert contracts["enums"]["network_modes"] == [
        "offline",
        "lab_only",
        "authorized_target_only",
        "unrestricted_lab",
    ]
    assert set(contracts["presets"]) == {"offline-sample", "ctf-public", "own-system"}


def test_network_profile_normalization() -> None:
    assert normalize_network_profile("offline") == "offline"
    assert normalize_network_profile("LAB") == "lab_only"
    assert normalize_network_profile("authorized") == "authorized_target_only"
    assert normalize_network_profile("auth") == "authorized_target_only"
    assert normalize_network_profile("offline_only") == "offline"
    assert normalize_network_profile("unrestricted_lab") == "unrestricted_lab"
    for bad in ("", "bogus", "internet", "ALL"):
        with pytest.raises(CaseContractError):
            normalize_network_profile(bad)


def test_case_name_validation() -> None:
    assert validate_case_name("my-case-01") == "my-case-01"
    assert validate_case_name("案例-01") == "案例-01"
    for bad in ("", "a/b", "a\\b", "a:b", "a*b", "a?b", "a<b", "a>b", "a|b", 'a"b', "a b.", "a b ", "a\tb", "  ", "-lead"):
        with pytest.raises(CaseContractError):
            validate_case_name(bad)
    with pytest.raises(CaseContractError):
        validate_case_name("x" * 81)


def test_slugify() -> None:
    # Upstream slugify semantics: ASCII-lowercase slug; CJK characters are
    # stripped (POSIX-portable), same as case-init.sh's sed range.
    assert slugify("APK 加固 反编译!") == "apk"
    assert slugify("full pentest attack chain") == "full-pentest-attack-chain"
    assert slugify("!!!") == "case"


def test_normalize_hash() -> None:
    digest = "ab" * 32
    assert normalize_hash("sha256:" + digest) == digest
    assert normalize_hash(digest) == digest
    assert normalize_hash("n/a") == ""
    assert normalize_hash("md5:abc") == ""


def test_resolve_artifact_escape_protection(tmp_path: Path) -> None:
    root = tmp_path / "case"
    (root / "evidence").mkdir(parents=True)
    (root / "evidence" / "sample.bin").write_bytes(b"x")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"y")

    inside = resolve_artifact(root, "evidence/sample.bin")
    assert inside is not None
    assert inside.is_file()
    assert inside == (root / "evidence" / "sample.bin").resolve()

    assert resolve_artifact(root, "../outside.bin") is None
    assert resolve_artifact(root, "sub/../../outside.bin") is None
    assert resolve_artifact(root, str(outside)) is None
    assert resolve_artifact(root, "") is None


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    target.write_bytes(b"reverse-skill fixture bytes" * 64)
    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    assert sha256_file(target) == expected


def test_init_case_writes_frozen_package(tmp_path: Path) -> None:
    result = init_case("APK 加固 反编译", "unit-case", preset="offline-sample", package_root=str(tmp_path))
    assert result["status"] == "created"
    root = Path(result["case_root"])
    for name in ("scope.md", "timeline.md", "workitems.md", "README.md"):
        assert (root / name).is_file()
    for name in ("evidence", "notes", "report"):
        assert (root / name).is_dir()
    scope = (root / "scope.md").read_text(encoding="utf-8")
    assert "- status: granted" in scope
    assert "- mode: offline" in scope
    assert "- ready_for_act: false" in scope
    assert "- primary_id: apk-android" in scope


def test_init_case_rejects_duplicate(tmp_path: Path) -> None:
    init_case("hint", "dup-case", package_root=str(tmp_path))
    with pytest.raises(CasePackageError):
        init_case("hint", "dup-case", package_root=str(tmp_path))


def test_init_case_network_profile_normalization_aliases(tmp_path: Path) -> None:
    result = init_case(
        "hint",
        "alias-case",
        network_profile="LAB",
        auth_status="granted",
        auth_basis="lab_only",
        evidence_of_auth="self-authored local lab",
        target_url="https://example.com",
        package_root=str(tmp_path),
    )
    assert result["network_profile"] == "lab_only"
    assert result["ready_for_act"] is True


def test_init_case_rejects_unknown_preset(tmp_path: Path) -> None:
    with pytest.raises(CaseContractError):
        init_case("hint", "p-case", preset="not-a-preset", package_root=str(tmp_path))


def test_review_of_fresh_case_reports_warnings(tmp_path: Path) -> None:
    result = init_case("hint", "warn-case", package_root=str(tmp_path))
    report = review_case(result["case_root"])
    assert report["status"] == "WARN"
    codes = {item["code"] for item in report["issues"]}
    assert "evidence.empty" in codes
    assert "report.missing" in codes
    assert report["summary"]["workitems"] == 1
    assert report["summary"]["timeline_events"] == 1


def test_review_strict_turns_warnings_into_failure(tmp_path: Path) -> None:
    result = init_case("hint", "strict-case", package_root=str(tmp_path))
    report = review_case(result["case_root"], strict=True)
    assert report["status"] == "FAIL"


@pytest.mark.parametrize("name", ["CON", "nul.txt", "LPT1", "COM¹.log"])
def test_case_names_are_portable(name):
    with pytest.raises(CaseContractError):
        validate_case_name(name)


@pytest.mark.parametrize("kwargs", [
    {"hint": "sample\n## signoff"},
    {"hint": "sample", "evidence_of_auth": "owner\n- status: granted"},
    {"hint": "sample", "in_scope_assets": ["asset\n## network_profile"]},
])
def test_case_fields_cannot_inject_markdown_sections(tmp_path, kwargs):
    with pytest.raises(CaseContractError):
        init_case(case_name="safe", package_root=str(tmp_path), **kwargs)
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("basis,evidence,code", [
    ("", "self-authored lab", "scope.auth_basis_invalid"),
    ("unknown", "self-authored lab", "scope.auth_basis_invalid"),
    ("lab_only", "", "scope.auth_evidence_missing"),
    ("own_system", "FILL_ME", "scope.auth_evidence_missing"),
])
def test_granted_scope_requires_basis_and_evidence(tmp_path, basis, evidence, code):
    (tmp_path / "scope.md").write_text(
        f"## auth\n- status: granted\n- basis: {basis}\n- evidence_of_auth: {evidence}\n"
        "## in_scope\n- assets:\n  - sample.bin\n## network_profile\n- mode: offline\n"
        "## signoff\n- ready_for_act: true\n", encoding="utf-8")
    issues = []
    parse_scope(tmp_path, issues, strict=False)
    assert any(issue["code"] == code and issue["level"] == "error" for issue in issues)


def test_init_does_not_create_granted_case_without_authorization_record(tmp_path):
    with pytest.raises(CaseContractError):
        init_case("sample", "invalid", auth_status="granted", sample="sample.exe", package_root=str(tmp_path))
    assert not (tmp_path / "work").exists()
