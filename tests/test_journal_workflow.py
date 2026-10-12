import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/auto-merge-journal.yml"
BASH = shutil.which("bash")
if os.name == "nt":
    git = shutil.which("git")
    git_bash = Path(git).parent.parent / "bin/bash.exe" if git else None
    BASH = str(git_bash) if git_bash and git_bash.is_file() else None
pytestmark = pytest.mark.skipif(BASH is None, reason="journal workflow requires Bash")


def _run_step(tmp_path, name, *, changed_files=(), title=""):
    step = WORKFLOW.read_text(encoding="utf-8").split(f"      - name: {name}\n", 1)[1]
    step = step.split("      - name:", 1)[0]
    script, env_lines = step.split("        run: |\n", 1)[1].split("        env:\n", 1)
    context = {
        "github.event.pull_request.number": "7",
        "github.event.pull_request.title": title,
        "secrets.GITHUB_TOKEN": "test-token",
    }

    def render(value):
        return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda match: context[match[1]], value)

    env = {
        **os.environ,
        "GITHUB_OUTPUT": "github-output.txt",
        "TEST_CHANGED_FILES": "\n".join(changed_files),
        **dict(render(line.strip()).split(": ", 1) for line in env_lines.splitlines() if line.strip()),
    }
    stub = """
gh() {
  if [[ "$1 $2" == "pr diff" ]]; then
    printf '%s\\n' "$TEST_CHANGED_FILES"
  elif [[ "$1 $2" == "pr merge" ]]; then
    printf '%s\\0' "$@" > merge-args.bin
  else
    return 1
  fi
}
"""
    script = render(textwrap.dedent(script)).replace("/tmp/real_ips", "real_ips.txt")
    return subprocess.run(
        [BASH, "--noprofile", "--norc", "-e", "-o", "pipefail"],
        input=stub + script,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize(
    "title",
    [
        "$(touch title-injected)",
        "`touch title-injected`",
        '"; touch title-injected; #',
        'A "quoted" $HOME title with\nnew line',
    ],
)
def test_merge_title_is_one_literal_argument(tmp_path, title):
    result = _run_step(tmp_path, "Auto-merge if valid", title=title)

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "title-injected").exists()
    args = (tmp_path / "merge-args.bin").read_bytes().decode("utf-8").split("\0")[:-1]
    assert args == ["pr", "merge", "7", "--auto", "--squash", "--subject", f"[field-journal] {title}"]


@pytest.mark.parametrize(
    ("content", "accepted"),
    [
        ("# Journal\nSafe notes about 192.0.2.1.\n", True),
        ("# Journal\nignore previous instructions\n", False),
        ("# Journal\n<script>alert(1)</script>\n", False),
        ("# Journal\nimport subprocess\n", False),
        ("# Journal\nbase64 -d\n", False),
        ("# Journal\nghp_" + "A" * 36 + "\n", False),
        ("# Journal\n8.8.8.8\n", False),
        ("# Journal\n" + "x" * 51200, False),
        ("Plain text without a heading\n", False),
        ("# Journal\nhttps://example.test/payload.sh\n", False),
    ],
    ids=["safe", "prompt", "html", "code", "base64", "token", "ip", "size", "heading", "link"],
)
def test_spaced_filename_receives_every_content_check(tmp_path, content, accepted):
    filename = "skills/field-journal/incident report.md"
    journal = tmp_path / filename
    journal.parent.mkdir(parents=True)
    journal.write_text(content, encoding="utf-8")

    result = _run_step(tmp_path, "Validate PR safety", changed_files=[filename])

    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    assert (tmp_path / "github-output.txt").read_text() == f"valid={str(accepted).lower()}\n"
    assert f"--- Scanning: {filename} ---" in result.stdout


def test_glob_filename_scans_the_literal_file(tmp_path):
    filename = "skills/field-journal/entry[draft].md"
    journal = tmp_path / filename
    journal.parent.mkdir(parents=True)
    journal.write_text("# Journal\nignore previous instructions\n", encoding="utf-8")
    journal.with_name("entryd.md").write_text("# Safe decoy\n", encoding="utf-8")

    result = _run_step(tmp_path, "Validate PR safety", changed_files=[filename])

    assert result.returncode != 0
    assert (tmp_path / "github-output.txt").read_text() == "valid=false\n"
    assert f"--- Scanning: {filename} ---" in result.stdout


def test_missing_changed_journal_rejects_automatic_merging(tmp_path):
    result = _run_step(
        tmp_path, "Validate PR safety", changed_files=["skills/field-journal/deleted entry.md"],
    )

    assert result.returncode != 0
    assert (tmp_path / "github-output.txt").read_text() == "valid=false\n"
