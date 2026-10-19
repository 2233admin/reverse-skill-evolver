"""Author-side unit tests for the frozen case contracts and parser internals."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from reverse_skill import case
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


def _evidence_record(evidence_id: str, digest: str, artifact: str) -> str:
    return f"""### {evidence_id}
- title: Sample hash
- severity: info
- status: observed
- content_hash: sha256:{digest}
- artifact_path: {artifact}
- linked_workitem: n/a
- repro_command: sha256sum {artifact}
- raw_excerpt: |
    fixture
"""


def _review_fixture(root: Path, records: int, artifact: Path, digest: str) -> None:
    """One case package whose Evidence records all point at the same artifact."""
    (root / "evidence").mkdir(parents=True)
    (root / "report").mkdir(parents=True)
    (root / "scope.md").write_text(
        "## auth\n- status: granted\n- basis: lab_only\n- evidence_of_auth: self-authored local fixture\n"
        "## in_scope\n- assets:\n  - sample.bin\n## network_profile\n- mode: offline\n"
        "## signoff\n- ready_for_act: true\n",
        encoding="utf-8",
    )
    (root / "workitems.md").write_text(
        "# Work Items\n\n| ID | title | role | targets | surface | status | evidence | notes |\n"
        "|----|-------|------|---------|---------|--------|----------|-------|\n",
        encoding="utf-8",
    )
    (root / "timeline.md").write_text("# Timeline (append-only)\n", encoding="utf-8")
    for index in range(records):
        (root / "evidence" / f"E-{index + 1:03d}.md").write_text(
            _evidence_record(f"E-{index + 1:03d}", digest, "evidence/sample.bin"), encoding="utf-8"
        )


def test_shared_artifact_is_hashed_once_per_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#23: 6 records on one artifact must read it once, not six times."""
    root = tmp_path / "shared-case"
    raw = b"reverse-skill shared artifact fixture" * 4096
    root.mkdir()
    _review_fixture(root, 6, root / "evidence" / "sample.bin", hashlib.sha256(raw).hexdigest())
    (root / "evidence" / "sample.bin").write_bytes(raw)

    reads = 0
    original = Path.open

    def counting_open(self: Path, *args: Any, **kwargs: Any):
        nonlocal reads
        if self.name == "sample.bin":
            reads += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    report = review_case(str(root), verify_hashes=True)

    assert report["status"] in {"PASS", "WARN"}
    assert not [item for item in report["issues"] if item["code"].startswith("artifact.")]
    assert reads == 1, f"artifact was opened {reads} times; expected one hash per review"


def test_cache_does_not_reuse_a_digest_after_the_artifact_changes(tmp_path: Path) -> None:
    """The cache's whole contract: reuse only while the file is byte-identical.

    Re-hashing a changed file is not evidence of anything — the uncached code does
    that too. What must hold is that a *populated* cache is invalidated by a
    rewrite, so this drives ``sha256_file`` directly rather than through a review.
    """
    artifact = tmp_path / "sample.bin"
    first = b"first state" * 2048
    artifact.write_bytes(first)
    cache: dict[str, Any] = {}

    first_digest = sha256_file(artifact, cache)
    assert first_digest == hashlib.sha256(first).hexdigest()
    assert sha256_file(artifact, cache) == first_digest  # cached, no re-read
    assert len(cache) == 1

    # Size and mtime both change, so the stale entry must not be returned.
    second = b"second state, different digest" * 2048
    artifact.write_bytes(second)
    second_digest = sha256_file(artifact, cache)

    assert second_digest == hashlib.sha256(second).hexdigest()
    assert second_digest != first_digest, "the cached digest was reused after an in-place rewrite"

    # A rollback to the original bytes must still verify against the original digest.
    artifact.write_bytes(first)
    assert sha256_file(artifact, cache) == first_digest


def test_cache_reacts_to_a_same_size_same_timestamp_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rewrite that preserves size must not be masked by a stale identity.

    Windows mtime granularity is coarse enough that two writes can land in the same
    tick. The cache compares the file against itself around the read instead of
    trusting a stored timestamp, so a same-size rewrite is still re-hashed when the
    identity is observed to differ.
    """
    artifact = tmp_path / "sample.bin"
    artifact.write_bytes(b"A" * 4096)
    cache: dict[str, Any] = {}
    before = sha256_file(artifact, cache)

    artifact.write_bytes(b"B" * 4096)  # identical size
    stat = artifact.stat()
    # Force an identity change even if the filesystem timestamp did not move.
    monkeypatch.setattr(
        case, "_file_identity", lambda _: (stat.st_size, stat.st_mtime_ns + 1)
    )
    after = sha256_file(artifact, cache)

    assert after != before, "a same-size rewrite must not return the cached digest"
    assert after == hashlib.sha256(b"B" * 4096).hexdigest()


def test_cache_is_never_populated_for_an_artifact_that_changed_while_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A digest that describes no single state must not be cached at all."""
    artifact = tmp_path / "sample.bin"
    artifact.write_bytes(b"x" * 4096)
    cache: dict[str, Any] = {}

    real_identity = case._file_identity
    calls = {"n": 0}

    def drifting_identity(path: Path):
        calls["n"] += 1
        value = real_identity(path)
        # Second call = the post-read check; report a different file.
        return value if calls["n"] == 1 else (value[0] + 1, value[1])

    monkeypatch.setattr(case, "_file_identity", drifting_identity)
    sha256_file(artifact, cache)

    assert cache[str(artifact)] is None, "an unverifiable digest must not be cached as valid"


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


def test_failed_case_write_is_retryable_and_preserves_other_cases(tmp_path, monkeypatch):
    parent = tmp_path / "work"
    parent.mkdir()
    sentinel = parent / "keep.txt"
    sentinel.write_text("user data")
    original = Path.write_text
    def fail_timeline(path, *args, **kwargs):
        if path.name == "timeline.md":
            raise OSError("simulated full disk")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", fail_timeline)
    with pytest.raises(CasePackageError):
        init_case("APK", "retry", package_root=str(tmp_path))
    assert not (parent / "retry").exists()
    assert sentinel.read_text() == "user data"
    monkeypatch.setattr(Path, "write_text", original)
    assert init_case("APK", "retry", package_root=str(tmp_path))["status"] == "created"
