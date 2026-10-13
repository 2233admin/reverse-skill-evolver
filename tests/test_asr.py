import json

import httpx
import pytest

from reverse_skill import asr_cli
from reverse_skill.asr import AsrClient, AsrTransportError, install_item
from reverse_skill.cli import main
from reverse_skill.errors import EnvironmentUnavailable, ToolOperationError


def item(item_id="sample", kind="skill", audited=True):
    return {
        "id": item_id, "name": "sample", "kind": kind, "is_audited": audited,
        "commit_sha": "abc123", "audited_by": "reviewer", "audited_at": "2026-10-14",
        "files": [{"filename": "SKILL.md", "file_type": "file", "content": "# sample\n"}],
    }


def test_list_follows_pages_filters_types_and_audit_and_deduplicates():
    seen = []

    def handler(request):
        seen.append(request)
        page = int(request.url.params["page"])
        rows = [item("first"), item("unreviewed", audited=False), item("server", kind="mcp")]
        if page == 2:
            rows = [item("first"), item("second", kind="goal"), item("third", kind="workflow")]
        return httpx.Response(200, json={"items": rows, "pagination": {"total_pages": 2, "page": page}})

    with AsrClient(api_key="private-key", transport=httpx.MockTransport(handler)) as client:
        data = client.list_items(search="current task")
    assert [row["id"] for row in data["items"]] == ["first", "second", "third"]
    assert data["pages_fetched"] == 2
    assert data["returned"] == 3
    assert data["filters"]["audited_only"] is True
    for request in seen:
        assert request.url.params["audited_only"] == "true"
        assert request.url.params["kind"] == "all"
        assert request.url.params["search"] == "current task"
        assert "authorization" not in request.headers


def test_single_page_and_kind_are_enforced_locally():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={
            "items": [item("s"), item("g", kind="goal")], "pagination": {"total_pages": 8},
        })

    with AsrClient(transport=httpx.MockTransport(handler)) as client:
        result = client.list_items(kind="goal", page=3, all_pages=False)
    assert [row["id"] for row in result["items"]] == ["g"]
    assert len(seen) == 1
    assert seen[0].url.params["page"] == "3"


@pytest.mark.parametrize("data", [
    {}, {"items": [], "pagination": {}}, {"items": [], "pagination": {"total_pages": "2"}},
    {"items": [None], "pagination": {"total_pages": 1}},
])
def test_bad_list_responses_fail_without_reporting_a_complete_catalog(data):
    with AsrClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))) as client:
        with pytest.raises(ToolOperationError):
            client.list_items()


@pytest.mark.parametrize("row", [item(audited=False), item(kind="mcp"), item("wrong-id")])
def test_show_and_install_script_reject_unreviewed_servers_and_wrong_ids(row):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=row)

    with AsrClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ToolOperationError):
            client.install_script("sample")
    assert len(seen) == 1


def test_all_asr_endpoint_requests_and_server_exclusion():
    seen = []

    def handler(request):
        seen.append(request)
        path = request.url.path
        if path == "/api/asr/sample":
            return httpx.Response(200, json=item())
        if path.endswith("/install"):
            return httpx.Response(200, text="Write-Output 'review me'")
        if path == "/api/asr/authors":
            return httpx.Response(200, json={"items": [{"top_items": [item(), item(audited=False)]}]})
        if path == "/api/asr/authors/owner":
            return httpx.Response(200, json={"items_list": [item(), item(kind="mcp")]})
        if path == "/api/asr/plugins/bundle":
            return httpx.Response(200, json={
                "members": [{"id": "skill", "is_audited": True}, {"id": "other", "is_audited": False}],
                "mcp_servers": [{"name": "server"}], "mcp_alerts": [{"server": "server"}],
                "is_audited": False, "guardrails": ["bundle verdict"],
            })
        return httpx.Response(200, json={"id": "result"})

    with AsrClient(api_key="secret", transport=httpx.MockTransport(handler)) as client:
        script = client.install_script("sample", location="global", harness="claude", shell="bash")
        assert script["script"] == "Write-Output 'review me'"
        assert len(client.authors(sort_by="downloads", page=2)["items"][0]["top_items"]) == 1
        assert len(client.author("owner")["items_list"]) == 1
        bundle = client.plugin("bundle")
        assert len(bundle["members"]) == 1
        assert "mcp_servers" not in bundle and "mcp_alerts" not in bundle
        assert bundle["is_audited"] is False
        assert bundle["guardrails"] == ["bundle verdict"]
        client.scans(search="repo", page=2, per_page=5, mine=True)
        client.scan("https://github.com/owner/repo", skill_path="skills/a", commit_sha="abc", plugin=True)
        client.scan_result("scan-id")
        client.import_repo("https://github.com/owner/repo", paths=["skills"], include_server=True)
        client.create_goal({"name": "bounded goal", "termination": {"max_turns": 3}})
        client.record_download("sample", "tests")
    by_path = {request.url.path: request for request in seen}
    assert dict(by_path["/api/asr/sample/install"].url.params) == {
        "location": "global", "harness": "claude", "shell": "bash",
    }
    scan = json.loads(by_path["/api/asr/scans"].content)
    assert scan["mcp"] is False and scan["plugin"] is True and scan["commit_sha"] == "abc"
    imported = json.loads(by_path["/api/asr/import"].content)
    assert imported["include_server"] is False
    assert imported["paths"] == ["skills"]
    assert by_path["/api/asr/import"].headers["authorization"] == "Bearer secret"
    assert by_path["/api/asr/goals"].headers["authorization"] == "Bearer secret"
    assert json.loads(by_path["/api/asr/sample/download"].content) == {"source": "tests"}


def test_missing_key_and_invalid_inputs_do_not_send_requests():
    seen = []
    with AsrClient(api_key="", transport=httpx.MockTransport(lambda request: seen.append(request))) as client:
        for operation in (
            lambda: client.import_repo("https://github.com/owner/repo"),
            lambda: client.create_goal({"name": "goal"}),
            lambda: client.list_items(mine=True),
        ):
            with pytest.raises(EnvironmentUnavailable):
                operation()
        for operation in (
            lambda: client.item("../scans"),
            lambda: client.scan("https://github.com.evil/owner/repo"),
            lambda: client.create_goal({"name": ""}),
        ):
            with pytest.raises(ToolOperationError):
                operation()
    assert seen == []


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_http_errors_are_actionable_and_never_echo_secrets(status):
    with AsrClient(api_key="super-secret", transport=httpx.MockTransport(lambda _: httpx.Response(
        status, text="super-secret", headers={"Retry-After": "7"},
    ))) as client:
        with pytest.raises(ToolOperationError, match=f"HTTP {status}") as error:
            client.author("owner")
    assert "super-secret" not in str(error.value)
    if status == 429:
        assert "retry after 7" in str(error.value)


def test_transport_and_malformed_json_errors():
    def handler(request):
        raise httpx.ConnectError("failure containing secret", request=request)

    with AsrClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AsrTransportError, match="ConnectError"):
            client.item("sample")
    with AsrClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>"))) as client:
        with pytest.raises(ToolOperationError, match="invalid JSON"):
            client.item("sample")


@pytest.mark.parametrize("kind,filename", [("skill", "SKILL.md"), ("goal", "goal.md"), ("workflow", "flow.js")])
def test_install_preserves_raw_files_without_executing_or_overwriting(tmp_path, kind, filename):
    row = item(kind=kind)
    row["files"] = [
        {"filename": filename, "file_type": "file", "content": "raw\ncontent\n"},
        {"filename": "references", "file_type": "directory", "content": ""},
        {"filename": "references/example.md", "file_type": "file", "content": "reference"},
    ]
    destination = tmp_path / "installed"
    result = install_item(row, destination)
    assert (destination / filename).read_text(encoding="utf-8") == "raw\ncontent\n"
    assert (destination / "references/example.md").read_text() == "reference"
    assert result["executed"] is False and result["commit_sha"] == "abc123"
    with pytest.raises(ToolOperationError, match="already exists"):
        install_item(row, destination)
    assert (destination / filename).read_text(encoding="utf-8") == "raw\ncontent\n"


@pytest.mark.parametrize("filename", [
    "../escape", "/absolute", "C:/outside", "a/../../escape", "a\\escape", "NUL.txt",
    "SKILL.md:payload", "folder/CON", "COM¹.txt", "folder/LPT²", "trailing. ",
    "a//b", "a/./b", "line\nname",
])
def test_install_rejects_unsafe_paths_before_writing(tmp_path, filename):
    row = item()
    row["files"].append({"filename": filename, "file_type": "file", "content": "bad"})
    with pytest.raises(ToolOperationError):
        install_item(row, tmp_path / "new-parent/installed")
    assert list(tmp_path.iterdir()) == []


def test_install_rejects_duplicate_names_and_missing_entries(tmp_path):
    row = item()
    row["files"].append({"filename": "skill.md", "file_type": "file", "content": "duplicate"})
    with pytest.raises(ToolOperationError, match="duplicate"):
        install_item(row, tmp_path / "installed")
    row["files"] = [{"filename": "notes.md", "file_type": "file", "content": "no entry"}]
    with pytest.raises(ToolOperationError, match="entry file"):
        install_item(row, tmp_path / "installed")


def test_asr_cli_success_and_error_use_existing_json_envelope(monkeypatch, capsys):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={
        "items": [item()], "pagination": {"total_pages": 1},
    }))
    monkeypatch.setattr(asr_cli, "AsrClient", lambda **options: AsrClient(transport=transport, **options))
    assert main(["--json", "asr", "list"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True and data["command"] == "asr"
    assert data["data"]["action"] == "list"
    assert data["data"]["result"]["returned"] == 1
    assert main(["--json", "asr", "list", "--kind", "mcp"]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["error"]["code"] == "usage"
    monkeypatch.delenv("FOREFY_API_KEY", raising=False)
    assert main(["--json", "asr", "import-repo", "https://github.com/owner/repo"]) == 3
    assert json.loads(capsys.readouterr().out)["command"] == "asr"


def test_create_goal_cli_reads_complete_definition(tmp_path, monkeypatch, capsys):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "new-goal", "goal_md": "/goal condition"})

    monkeypatch.setenv("FOREFY_API_KEY", "test-key")
    monkeypatch.setattr(asr_cli, "AsrClient", lambda **options: AsrClient(
        transport=httpx.MockTransport(handler), **options,
    ))
    definition = {"name": "goal", "proof": ["tests pass"], "termination": {"max_turns": 2}}
    path = tmp_path / "goal.json"
    path.write_text(json.dumps(definition), encoding="utf-8-sig")
    assert main(["--json", "asr", "create-goal", "--input", str(path)]) == 0
    assert seen == [definition]
    assert json.loads(capsys.readouterr().out)["data"]["result"]["id"] == "new-goal"


@pytest.mark.parametrize("arguments,path,expected", [
    (["scan", "https://github.com/owner/repo", "--commit-sha", "abc", "--skill-path", "plugins/a", "--plugin"],
     "/api/asr/scans", {"github_url": "https://github.com/owner/repo", "commit_sha": "abc",
                        "skill_path": "plugins/a", "plugin": True, "mcp": False}),
    (["import-repo", "https://github.com/owner/repo", "--path", "skills/a", "--path", "skills/b",
      "--skill-name", "a", "--is-benchmark", "--parent-benchmark-id", "parent"],
     "/api/asr/import", {"github_url": "https://github.com/owner/repo", "paths": ["skills/a", "skills/b"],
                         "skill_names": ["a"], "is_benchmark": True, "parent_benchmark_id": "parent",
                         "include_server": False}),
    (["record-download", "sample", "--source", "tests"],
     "/api/asr/sample/download", {"source": "tests"}),
])
def test_write_commands_forward_the_reviewable_payload(arguments, path, expected, monkeypatch, capsys):
    seen = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=item())
        seen.append(request)
        return httpx.Response(200, json={"id": "submitted"})

    monkeypatch.setenv("FOREFY_API_KEY", "test-key")
    monkeypatch.setattr(asr_cli, "AsrClient", lambda **options: AsrClient(
        transport=httpx.MockTransport(handler), **options,
    ))
    assert main(["--json", "asr", *arguments]) == 0
    assert len(seen) == 1 and seen[0].method == "POST" and seen[0].url.path == path
    assert json.loads(seen[0].content) == expected
    assert ("authorization" in seen[0].headers) == (arguments[0] == "import-repo")
    assert json.loads(capsys.readouterr().out)["data"]["action"] == arguments[0]
