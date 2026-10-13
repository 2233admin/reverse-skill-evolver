from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import httpx

from .errors import EnvironmentUnavailable, ReverseSkillError, ToolOperationError


KINDS = ("skill", "goal", "workflow")
BASE_URL = "https://forefy.com"


class AsrTransportError(ReverseSkillError):
    exit_code = 4


class AsrClient:
    """Access ASR without executing registry content or importing MCP servers."""

    def __init__(
        self, *, timeout: float = 120, api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("FOREFY_API_KEY")
        self.http = httpx.Client(base_url=BASE_URL, timeout=timeout, transport=transport)

    def __enter__(self) -> AsrClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.http.close()

    def request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None, auth: bool = False, text: bool = False,
    ) -> Any:
        if auth and not self.api_key:
            raise EnvironmentUnavailable("This ASR operation requires FOREFY_API_KEY (full-account key).")
        headers = {"Authorization": f"Bearer {self.api_key}"} if auth else {}
        try:
            response = self.http.request(method, path, params=params, json=body, headers=headers)
        except httpx.RequestError as exc:
            raise AsrTransportError(f"ASR request failed: {type(exc).__name__}") from exc
        if not response.is_success:
            retry = response.headers.get("retry-after")
            hint = f"; retry after {retry} seconds" if response.status_code == 429 and retry else ""
            if response.status_code in (401, 403):
                hint = "; check FOREFY_API_KEY expiry and full-account scope"
            raise ToolOperationError(f"ASR {method} {path}: HTTP {response.status_code}{hint}")
        if text:
            return response.text
        try:
            data = response.json()
        except ValueError as exc:
            raise ToolOperationError("ASR returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise ToolOperationError("ASR returned a JSON value that is not an object.")
        return data

    def list_items(
        self, *, kind: str = "all", search: str = "", sort_by: str = "audited",
        page: int = 1, per_page: int = 100, all_pages: bool = True, mine: bool = False,
    ) -> dict[str, Any]:
        if kind not in (*KINDS, "all"):
            raise ToolOperationError("ASR kind must be skill, goal, workflow, or all.")
        items: dict[str, dict[str, Any]] = {}
        pages_fetched = 0
        while True:
            data = self.request("GET", "/api/asr", params={
                "kind": kind, "search": search, "sort_by": sort_by,
                "audited_only": "true", "page": page, "per_page": per_page,
                "mine": str(mine).lower(),
            }, auth=mine)
            rows, pagination = data.get("items"), data.get("pagination")
            if not isinstance(rows, list) or not isinstance(pagination, dict):
                raise ToolOperationError("ASR list response is missing items or pagination.")
            total_pages = pagination.get("total_pages")
            if type(total_pages) is not int or not 0 <= total_pages <= 1000:
                raise ToolOperationError("ASR returned invalid pagination (maximum 1000 pages).")
            for item in audited_items(rows):
                if kind == "all" or item["kind"] == kind:
                    identifier(item.get("id"))
                    items[item["id"]] = item
            pages_fetched += 1
            if not all_pages or page >= total_pages:
                break
            page += 1
        return {
            "items": list(items.values()), "pagination": pagination,
            "pages_fetched": pages_fetched, "returned": len(items),
            "filters": {"audited_only": True, "exclude_mcp_servers": True, "kind": kind},
        }

    def item(self, item_id: str) -> dict[str, Any]:
        data = self.request("GET", f"/api/asr/{identifier(item_id)}")
        if data.get("is_audited") is not True or data.get("kind") not in KINDS:
            raise ToolOperationError("ASR item must be audited and a skill, goal, or workflow.")
        if data.get("id") != item_id:
            raise ToolOperationError("ASR returned a different item id.")
        return data

    def install_script(
        self, item_id: str, *, location: str = "project", harness: str = "agents",
        shell: str = "powershell",
    ) -> dict[str, Any]:
        item = self.item(item_id)
        script = self.request("GET", f"/api/asr/{identifier(item_id)}/install", params={
            "location": location, "harness": harness, "shell": shell,
        }, text=True)
        return {"id": item_id, "is_audited": True, "kind": item["kind"], "script": script}

    def authors(self, **params: Any) -> dict[str, Any]:
        data = self.request("GET", "/api/asr/authors", params=params)
        if not isinstance(data.get("items"), list):
            raise ToolOperationError("ASR authors response is missing items.")
        for author in data["items"]:
            if not isinstance(author, dict):
                raise ToolOperationError("ASR returned an invalid author.")
            author["top_items"] = audited_items(author.get("top_items", []))
        return data

    def author(self, key: str) -> dict[str, Any]:
        data = self.request("GET", f"/api/asr/authors/{identifier(key)}")
        data["items_list"] = audited_items(data.get("items_list", []))
        return data

    def plugin(self, plugin_id: str) -> dict[str, Any]:
        data = self.request("GET", f"/api/asr/plugins/{identifier(plugin_id)}")
        # ASR plugin members are skills; this endpoint omits their kind field.
        members = data.get("members", [])
        if not isinstance(members, list) or any(not isinstance(row, dict) for row in members):
            raise ToolOperationError("ASR returned invalid plugin members.")
        data["members"] = audited_items([{"kind": "skill", **row} for row in members])
        data.pop("mcp_servers", None)
        data.pop("mcp_alerts", None)
        data["filters"] = {"audited_only": True, "exclude_mcp_servers": True}
        return data

    def scans(self, **params: Any) -> dict[str, Any]:
        return self.request("GET", "/api/asr/scans", params=params, auth=bool(params.get("mine")))

    def scan(self, github_url: str, **options: Any) -> dict[str, Any]:
        return self.request("POST", "/api/asr/scans", body={
            **options, "github_url": repository_url(github_url), "mcp": False,
        })

    def scan_result(self, scan_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/asr/scans/{identifier(scan_id)}")

    def import_repo(self, github_url: str, **options: Any) -> dict[str, Any]:
        return self.request("POST", "/api/asr/import", body={
            **options, "github_url": repository_url(github_url), "include_server": False,
        }, auth=True)

    def create_goal(self, body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body.get("name"), str) or not body["name"].strip():
            raise ToolOperationError("ASR goal definition requires a non-empty name.")
        return self.request("POST", "/api/asr/goals", body=body, auth=True)

    def record_download(self, item_id: str, source: str) -> dict[str, Any]:
        self.item(item_id)
        return self.request("POST", f"/api/asr/{identifier(item_id)}/download", body={"source": source})


def audited_items(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ToolOperationError("ASR returned invalid registry items.")
    return [row for row in rows if row.get("is_audited") is True and row.get("kind") in KINDS]


def identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ToolOperationError("Invalid ASR identifier.")
    return value


def repository_url(value: str) -> str:
    parsed = urlsplit(value)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https" or parsed.netloc != "github.com" or len(parts) < 2
        or parsed.query or parsed.fragment or any(part in (".", "..") for part in parts)
    ):
        raise ToolOperationError("Expected an HTTPS github.com repository URL.")
    return value


def install_item(item: dict[str, Any], destination: Path) -> dict[str, Any]:
    """Save audited raw files into a new directory; never run remote install scripts."""
    if item.get("is_audited") is not True or item.get("kind") not in KINDS:
        raise ToolOperationError("Only audited ASR skills, goals, and workflows can be installed.")
    files = item.get("files")
    if not isinstance(files, list) or not files:
        raise ToolOperationError("ASR item has no installable raw files; inspect install-script instead.")
    content: dict[Path, str] = {}
    seen: set[str] = set()
    for file in files:
        if not isinstance(file, dict):
            raise ToolOperationError("ASR returned an invalid file.")
        name = file.get("filename")
        if not isinstance(name, str) or not name or "\\" in name:
            raise ToolOperationError("ASR returned an unsafe filename.")
        path = PurePosixPath(name)
        if path.is_absolute() or any(not safe_filename(part) for part in name.split("/")):
            raise ToolOperationError(f"Unsafe ASR filename: {name!r}")
        if name.casefold() in seen:
            raise ToolOperationError("ASR returned duplicate filenames.")
        seen.add(name.casefold())
        if file.get("file_type") == "directory":
            continue
        if file.get("file_type") != "file" or not isinstance(file.get("content"), str):
            raise ToolOperationError("ASR file is not supported as raw text.")
        content[Path(*path.parts)] = file["content"]
    names = {str(path).replace("\\", "/") for path in content}
    required = {"skill": "SKILL.md", "goal": "goal.md"}.get(item["kind"])
    if (required and required not in names) or (item["kind"] == "workflow" and not any(
        path.endswith(".js") for path in names
    )):
        raise ToolOperationError("ASR item is missing its skill, goal, or workflow entry file.")
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ToolOperationError(f"Install destination already exists: {destination}")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="asr-", dir=destination.parent) as temporary:
            stage = Path(temporary) / "item"
            stage.mkdir()
            for path, value in content.items():
                target = stage / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(value.encode("utf-8"))
            stage.rename(destination)
    except (OSError, UnicodeError) as exc:
        raise ToolOperationError(f"Cannot install ASR files: {exc}") from exc
    return {
        "id": item["id"], "kind": item["kind"], "is_audited": True,
        "audited_by": item.get("audited_by"), "audited_at": item.get("audited_at"),
        "github_url": item.get("github_url"), "commit_sha": item.get("commit_sha"),
        "destination": str(destination), "files": sorted(names), "executed": False,
    }


def safe_filename(part: str) -> bool:
    return (
        part not in ("", ".", "..") and not part.endswith((".", " "))
        and not re.search(r'[<>:"|?*\x00-\x1f]', part)
        and not re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]", part.split(".")[0], re.I)
    )
