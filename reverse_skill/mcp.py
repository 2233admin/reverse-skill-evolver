from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import httpx

from .errors import McpProtocolError, McpTransportError, ToolOperationError


MODERN_VERSION = "2026-07-28"
LEGACY_VERSIONS = {"2025-11-25", "2025-06-18", "2025-03-26"}
MODERN_ERROR_CODES = {-32020, -32021, -32022}
HEADER_TOKEN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
SAFE_INTEGER = 9_007_199_254_740_991


@dataclass
class HttpResult:
    status_code: int
    headers: Mapping[str, str]
    message: dict[str, Any] | None
    content_type: str
    raw_content: str


def encode_header_value(value: str) -> str:
    plain = (
        bool(value)
        and value == value.strip()
        and all(char == "\t" or " " <= char <= "~" for char in value)
        and not re.fullmatch(r"=\?base64\?.*\?=", value)
    )
    if plain:
        return value
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"=?base64?{encoded}?="


def encode_parameter_header(value: Any, value_type: str) -> str:
    if value_type == "boolean":
        if type(value) is not bool:
            raise McpProtocolError("x-mcp-header boolean parameter value is not a Boolean")
        text = "true" if value else "false"
    elif value_type == "integer":
        if type(value) is not int or abs(value) > SAFE_INTEGER:
            raise McpProtocolError("x-mcp-header integer parameter is outside the JavaScript safe integer range")
        text = str(value)
    else:
        if not isinstance(value, str):
            raise McpProtocolError("x-mcp-header string parameter value is not a String")
        text = value
    return encode_header_value(text)


class McpClient:
    def __init__(
        self,
        url: str = "http://127.0.0.1:13337/mcp",
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        client_name: str = "reverse-skill-cli",
        client_version: str = "1.0.0",
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.era = "modern"
        self.protocol_version = MODERN_VERSION
        self.session_id = ""
        self.next_request_id = 2
        self.client_info = {"name": client_name, "version": client_version}
        self.client_capabilities: dict[str, Any] = {}
        self.server_info: dict[str, Any] | None = None
        self.capabilities: dict[str, Any] | None = None
        self.tool_headers: dict[str, list[dict[str, Any]]] = {}
        self.http = httpx.Client(timeout=timeout, transport=transport)
        if not self._discover_modern():
            self._initialize_legacy()

    def __enter__(self) -> "McpClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _next_id(self) -> str | int:
        if self.era == "modern":
            return uuid.uuid4().hex
        request_id = self.next_request_id
        self.next_request_id += 1
        return request_id

    def _params(self, params: Mapping[str, Any] | None) -> dict[str, Any]:
        result = dict(params or {})
        if self.era == "modern":
            meta = dict(result.get("_meta") or {})
            meta.update(
                {
                    "io.modelcontextprotocol/protocolVersion": self.protocol_version,
                    "io.modelcontextprotocol/clientInfo": self.client_info,
                    "io.modelcontextprotocol/clientCapabilities": self.client_capabilities,
                }
            )
            result["_meta"] = meta
        return result

    def _message(self, request_id: str | int, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": self._params(params)}

    @staticmethod
    def _parse_response(content: str, content_type: str, request_id: str | int | None) -> dict[str, Any] | None:
        # JSON-RPC notifications do not have a response body. Some legacy MCP
        # servers acknowledge them with the literal HTTP body ``Accepted``.
        if request_id is None:
            return None
        if not content.strip():
            return None
        if content_type.lower().startswith("text/event-stream"):
            messages: list[dict[str, Any]] = []
            data_lines: list[str] = []
            for line in content.splitlines() + [""]:
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip(" "))
                elif not line.strip() and data_lines:
                    messages.append(json.loads("\n".join(data_lines)))
                    data_lines.clear()
            if request_id is None and messages:
                return messages[-1]
            for message in messages:
                if str(message.get("id")) == str(request_id):
                    return message
            raise McpProtocolError(f"MCP SSE response did not contain JSON-RPC id {request_id}")

        message = json.loads(content)
        if not isinstance(message, dict):
            raise McpProtocolError("MCP JSON response is not an object")
        if request_id is not None and str(message.get("id")) != str(request_id):
            raise McpProtocolError(f"MCP JSON response did not contain JSON-RPC id {request_id}")
        return message

    def _send(self, message: Mapping[str, Any], extra_headers: Mapping[str, str] | None = None) -> HttpResult:
        method = str(message["method"])
        headers = {"Accept": "application/json, text/event-stream", "Mcp-Method": method}
        if self.era == "legacy" and self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol_version and (self.era == "modern" or method != "initialize"):
            headers["MCP-Protocol-Version"] = self.protocol_version

        params = message.get("params")
        name = None
        if isinstance(params, Mapping):
            if method in {"tools/call", "prompts/get"}:
                name = params.get("name")
            elif method == "resources/read":
                name = params.get("uri")
        if name is not None:
            headers["Mcp-Name"] = encode_header_value(str(name))
        headers.update(extra_headers or {})

        try:
            response = self.http.post(self.url, headers=headers, json=message)
        except httpx.RequestError as exc:
            raise McpTransportError(f"MCP request failed: {exc}") from exc

        request_id = message.get("id")
        try:
            parsed = self._parse_response(response.text, response.headers.get("content-type", ""), request_id)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise McpProtocolError(f"MCP response is not valid JSON: {exc}") from exc
        return HttpResult(
            status_code=response.status_code,
            headers=response.headers,
            message=parsed,
            content_type=response.headers.get("content-type", ""),
            raw_content=response.text,
        )

    def _discover_modern(self) -> bool:
        for _ in range(2):
            response = self._send(self._message(self._next_id(), "server/discover"))
            if response.message is None:
                raise McpProtocolError(
                    f"MCP modern discovery failed: HTTP {response.status_code} returned no JSON-RPC response"
                )
            result = response.message.get("result")
            error = response.message.get("error")
            if isinstance(result, Mapping):
                if result.get("resultType") != "complete":
                    return False
                versions = result.get("supportedVersions") or []
                if MODERN_VERSION not in versions:
                    raise McpProtocolError("modern server did not advertise a mutually supported protocol version")
                self.protocol_version = MODERN_VERSION
                self.capabilities = dict(result.get("capabilities") or {})
                meta = result.get("_meta") or {}
                if isinstance(meta, Mapping):
                    info = meta.get("io.modelcontextprotocol/serverInfo")
                    self.server_info = dict(info) if isinstance(info, Mapping) else None
                return True
            if isinstance(error, Mapping) and error.get("code") in MODERN_ERROR_CODES:
                if error.get("code") == -32022:
                    data = error.get("data") or {}
                    supported = data.get("supported") if isinstance(data, Mapping) else []
                    if MODERN_VERSION in (supported or []) and self.protocol_version != MODERN_VERSION:
                        self.protocol_version = MODERN_VERSION
                        continue
                raise McpProtocolError(f"MCP modern discovery failed: {json.dumps(error, ensure_ascii=False)}")
            return False
        raise McpProtocolError("MCP modern protocol negotiation did not converge")

    def _initialize_legacy(self) -> None:
        self.era = "legacy"
        self.protocol_version = ""
        self.session_id = ""
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": self.client_info,
            },
        }
        response = self._send(message)
        if not response.message or response.message.get("error"):
            raise McpProtocolError("MCP legacy initialize failed")
        result = response.message.get("result") or {}
        negotiated = result.get("protocolVersion")
        if negotiated not in LEGACY_VERSIONS:
            raise McpProtocolError(f"server negotiated unsupported legacy protocol version: {negotiated}")
        self.protocol_version = str(negotiated)
        self.session_id = response.headers.get("Mcp-Session-Id", "")
        self.server_info = dict(result.get("serverInfo") or {})
        self.capabilities = dict(result.get("capabilities") or {})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._send(self._message(self._next_id(), method, params), extra_headers)
        if response.message is None:
            raise McpProtocolError(f"MCP {method} returned no JSON-RPC response (HTTP {response.status_code})")
        if response.message.get("error") is not None:
            raise McpProtocolError(
                f"MCP {method} failed: {json.dumps(response.message['error'], ensure_ascii=False)}"
            )
        result = response.message.get("result")
        if not isinstance(result, dict):
            raise McpProtocolError(f"MCP {method} result is not an object")
        if self.era == "modern" and method == "tools/list":
            self._register_tool_definitions(result)
        return result

    def _header_annotations(self, tool: Mapping[str, Any]) -> list[dict[str, Any]]:
        annotations: list[dict[str, Any]] = []
        names: set[str] = set()

        def visit(node: Any, path: list[str], static: bool, property_schema: bool) -> None:
            if isinstance(node, list):
                for child in node:
                    visit(child, path, False, False)
                return
            if not isinstance(node, Mapping):
                return
            if "x-mcp-header" in node:
                if not static or not property_schema:
                    raise ValueError("x-mcp-header is not on a statically reachable properties path")
                name = node["x-mcp-header"]
                if not isinstance(name, str) or not name or not HEADER_TOKEN.fullmatch(name):
                    raise ValueError("x-mcp-header name must be a non-empty RFC token string")
                lowered = name.casefold()
                if lowered in names:
                    raise ValueError(f"duplicate x-mcp-header name: {name}")
                names.add(lowered)
                value_type = node.get("type")
                if value_type not in {"string", "integer", "boolean"}:
                    raise ValueError(f"x-mcp-header {name} uses unsupported type: {value_type}")
                annotations.append({"header": name, "path": tuple(path), "type": value_type})
            for key, value in node.items():
                if key == "x-mcp-header":
                    continue
                if key == "properties" and isinstance(value, Mapping):
                    for property_name, property_value in value.items():
                        visit(property_value, [*path, str(property_name)], static, static)
                else:
                    visit(value, path, False, False)

        visit(tool.get("inputSchema"), [], True, False)
        return annotations

    def _register_tool_definitions(self, result: dict[str, Any]) -> None:
        valid: list[dict[str, Any]] = []
        for tool in result.get("tools") or []:
            if not isinstance(tool, Mapping) or not isinstance(tool.get("name"), str):
                continue
            name = str(tool["name"])
            try:
                self.tool_headers[name] = self._header_annotations(tool)
            except ValueError:
                continue
            valid.append(dict(tool))
        result["tools"] = valid

    def _ensure_tool(self, name: str) -> None:
        if self.era != "modern" or name in self.tool_headers:
            return
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            result = self.request("tools/list", {"cursor": cursor} if cursor else None)
            if name in self.tool_headers:
                return
            cursor = result.get("nextCursor")
            if not cursor:
                break
            if cursor in seen:
                raise McpProtocolError("MCP tools/list returned a repeated pagination cursor")
            seen.add(cursor)
        raise McpProtocolError(f"MCP tool {name!r} is unavailable or has an invalid x-mcp-header definition")

    @staticmethod
    def _nested(arguments: Mapping[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
        current: Any = arguments
        for segment in path:
            if not isinstance(current, Mapping) or segment not in current:
                return False, None
            current = current[segment]
        return True, current

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        input_responses: Mapping[str, Any] | None = None,
        request_state: str | None = None,
    ) -> dict[str, Any]:
        if self.era != "modern" and (input_responses is not None or request_state is not None):
            raise McpProtocolError("MRTR inputResponses/requestState require MCP 2026-07-28 or newer")
        tool_arguments = dict(arguments or {})
        self._ensure_tool(name)
        params: dict[str, Any] = {"name": name, "arguments": tool_arguments}
        if input_responses is not None:
            params["inputResponses"] = dict(input_responses)
        if request_state is not None:
            params["requestState"] = request_state

        headers: dict[str, str] = {}
        if self.era == "modern":
            for annotation in self.tool_headers.get(name, []):
                exists, value = self._nested(tool_arguments, annotation["path"])
                if exists and value is not None:
                    headers[f"Mcp-Param-{annotation['header']}"] = encode_parameter_header(
                        value, annotation["type"]
                    )
        result = self.request("tools/call", params, extra_headers=headers)
        if result.get("resultType") == "input_required":
            return result
        if result.get("isError") is True:
            detail = ((result.get("structuredContent") or {}).get("error"))
            if not detail:
                detail = "; ".join(str(item.get("text", "")) for item in result.get("content") or [])
            raise ToolOperationError(f"MCP tool {name} failed: {detail}")
        return result

    def close(self) -> None:
        try:
            if self.era == "legacy" and self.session_id:
                try:
                    self.http.delete(
                        self.url,
                        headers={
                            "Mcp-Session-Id": self.session_id,
                            "MCP-Protocol-Version": self.protocol_version,
                        },
                        timeout=min(self.timeout, 10),
                    )
                except httpx.RequestError:
                    pass
        finally:
            self.http.close()


def probe_tool_count(port: int, timeout: float) -> int:
    try:
        with McpClient(f"http://127.0.0.1:{port}/mcp", timeout=timeout) as client:
            return len(client.request("tools/list").get("tools") or [])
    except (McpProtocolError, McpTransportError):
        return -1


def create_index_mcp_server() -> Any:
    """Create the optional MCP 2.0 read-only index adapter.

    The adapter deliberately delegates every operation to ``index_api``. It
    exposes no build/update tools, so a client cannot mutate an index through
    the first MCP surface.
    """
    try:
        from mcp.server import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised by the CLI smoke
        raise McpTransportError(
            "MCP 2.0 adapter is unavailable; install the optional 'mcp' extra"
        ) from exc

    from . import __version__, index_api

    server = MCPServer(
        "reverse-skill-index",
        description="Read-only deterministic reverse-skill workspace index",
        version=__version__,
    )

    def optional_path(value: str | None) -> Path | None:
        return Path(value) if value else None

    @server.tool(
        name="index_status",
        description="Read index freshness, capability, and counts without building it.",
        structured_output=True,
    )
    def index_status(root: str, index_path: str | None = None) -> dict[str, Any]:
        return index_api.index_status(Path(root), optional_path(index_path))

    @server.tool(
        name="index_search",
        description="Search the deterministic local index with BM25, tree, or hybrid retrieval.",
        structured_output=True,
    )
    def index_search(
        root: str,
        query: str,
        mode: str = "hybrid",
        top_k: int | None = None,
        index_path: str | None = None,
    ) -> dict[str, Any]:
        return index_api.index_search(
            Path(root), query, mode, top_k, optional_path(index_path)
        )

    @server.tool(
        name="index_get_tree",
        description="Read one indexed node with its ancestors and bounded descendants.",
        structured_output=True,
    )
    def index_get_tree(
        root: str, node_id: str, index_path: str | None = None
    ) -> dict[str, Any]:
        return index_api.index_get_tree(Path(root), node_id, optional_path(index_path))

    @server.tool(
        name="index_read_nodes",
        description="Read indexed node metadata and text by stable node IDs.",
        structured_output=True,
    )
    def index_read_nodes(
        root: str, node_ids: list[str], index_path: str | None = None
    ) -> dict[str, Any]:
        return index_api.index_read_nodes(
            Path(root), node_ids, optional_path(index_path)
        )

    return server


def mcp_main(argv: list[str] | None = None) -> int:
    """Run the optional MCP adapter over stdio or Streamable HTTP."""
    parser = argparse.ArgumentParser(description="Run the reverse-skill MCP 2.0 index adapter")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport (legacy HTTP+SSE is intentionally not exposed)",
    )
    args = parser.parse_args(argv)
    try:
        server = create_index_mcp_server()
    except McpTransportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    server.run(args.transport)
    return 0
