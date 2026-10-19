from __future__ import annotations

import base64
import asyncio
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from .errors import McpError, McpProtocolError, McpTransportError, ToolOperationError


MODERN_VERSION = "2026-07-28"
LEGACY_VERSIONS = {"2025-11-25", "2025-06-18", "2025-03-26"}
MODERN_ERROR_CODES = {-32020, -32021, -32022}
HEADER_TOKEN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
SAFE_INTEGER = 9_007_199_254_740_991

# The deadline bounds waiting time, not memory: a fast sender can keep every
# per-chunk deadline check satisfied while the buffer grows without limit, and a
# single SSE event streamed as one long line is unbounded even with an event cap.
# Both budgets are therefore checked while accumulating, and exceeding one fails
# loudly with the observed size instead of truncating silently.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_SSE_EVENTS = 4096


class _NetworkStream(httpx.SyncByteStream):
    def __init__(self, transport: "_NetworkTransport", response: httpx.Response) -> None:
        self.transport = transport
        self.response = response

    def __iter__(self):
        iterator = self.response.aiter_raw()
        while True:
            try:
                yield self.transport.run(iterator.__anext__())
            except StopAsyncIteration:
                return

    def close(self) -> None:
        self.transport.run(self.response.aclose(), cleanup=True)


class _CheckedStream(httpx.SyncByteStream):
    def __init__(self, stream: httpx.SyncByteStream, check) -> None:
        self.stream = stream
        self.check = check

    def __iter__(self):
        for chunk in self.stream:
            self.check()
            yield chunk
        self.check()

    def close(self) -> None:
        self.stream.close()


class _NetworkTransport(httpx.BaseTransport):
    """Drive cancellable HTTPX I/O while keeping the caller's synchronous API."""

    def __init__(self, deadline: float | None) -> None:
        self.deadline = deadline
        self.loop = None
        self.thread = None
        self.client = None

    def run(self, operation, *, cleanup=False):
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            self.thread = threading.Thread(target=self.loop.run_forever, name="mcp-http", daemon=True)
            self.thread.start()

        async def wait():
            if cleanup or self.deadline is None:
                return await operation
            # wait_for is available on Python 3.10 and cancels pending network I/O.
            return await asyncio.wait_for(operation, max(0, self.deadline - time.monotonic()))

        try:
            return asyncio.run_coroutine_threadsafe(wait(), self.loop).result()
        except asyncio.TimeoutError as exc:
            raise httpx.TimeoutException("MCP probe deadline exceeded") from exc

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        async def send():
            if self.client is None:
                self.client = httpx.AsyncClient()
            outgoing = httpx.Request(
                request.method, request.url, headers=request.headers,
                content=request.content, extensions=request.extensions,
            )
            return await self.client.send(outgoing, stream=True)

        response = self.run(send())
        return httpx.Response(
            response.status_code, headers=response.headers,
            stream=_NetworkStream(self, response), extensions=response.extensions,
        )

    def close(self) -> None:
        if self.loop is None:
            return
        try:
            if self.client is not None:
                self.run(self.client.aclose(), cleanup=True)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join()
            self.loop.close()
            self.loop = self.thread = self.client = None


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
        deadline: float | None = None,
        transport: httpx.BaseTransport | None = None,
        client_name: str = "reverse-skill-cli",
        client_version: str = "1.0.0",
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.deadline = deadline
        self.era = "modern"
        self.protocol_version = MODERN_VERSION
        self.session_id = ""
        self.next_request_id = 2
        self.client_info = {"name": client_name, "version": client_version}
        self.client_capabilities: dict[str, Any] = {}
        self.server_info: dict[str, Any] | None = None
        self.capabilities: dict[str, Any] | None = None
        self.tool_headers: dict[str, list[dict[str, Any]]] = {}
        self._network = _NetworkTransport(deadline) if transport is None else None
        self.http = httpx.Client(timeout=timeout, transport=transport if transport is not None else self._network)
        try:
            if not self._discover_modern():
                self._initialize_legacy()
        except BaseException:
            try:
                self.http.close()
            except Exception:
                pass
            finally:
                if self._network is not None:
                    self._network.close()
            raise

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
            matched_message: dict[str, Any] | None = None
            selection_error: AttributeError | None = None
            data_lines: list[str] = []
            for line in content.splitlines() + [""]:
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip(" "))
                elif not line.strip() and data_lines:
                    message = json.loads("\n".join(data_lines))
                    data_lines.clear()
                    if matched_message is None and selection_error is None:
                        try:
                            if str(message.get("id")) == str(request_id):
                                matched_message = message
                        except AttributeError as exc:
                            # Validate all event JSON before reporting selection errors.
                            selection_error = exc.with_traceback(None)
                    del message
            if selection_error is not None:
                raise selection_error
            if matched_message is not None:
                return matched_message
            raise McpProtocolError(f"MCP SSE response did not contain JSON-RPC id {request_id}")

        message = json.loads(content)
        if not isinstance(message, dict):
            raise McpProtocolError("MCP JSON response is not an object")
        if request_id is not None and str(message.get("id")) != str(request_id):
            raise McpProtocolError(f"MCP JSON response did not contain JSON-RPC id {request_id}")
        return message

    def _remaining_timeout(self) -> float:
        return self.timeout if self.deadline is None else min(self.timeout, self.deadline - time.monotonic())

    def _check_deadline(self) -> None:
        if self._remaining_timeout() <= 0:
            raise McpTransportError("MCP probe deadline exceeded")

    def _read_response(self, response: httpx.Response, request_id: str | int | None):
        if request_id is None:
            return None, ""
        content_type = response.headers.get("content-type", "")
        # Read before consuming the stream: a failure path must not touch it afterwards.
        encoding = response.encoding or "utf-8"
        if content_type.lower().startswith("text/event-stream"):
            data_lines: list[str] = []
            events = 0
            consumed = 0
            for line in response.iter_lines():
                self._check_deadline()
                consumed += len(line.encode("utf-8", "replace"))
                if consumed > MAX_RESPONSE_BYTES:
                    raise McpProtocolError(
                        f"MCP SSE response exceeded {MAX_RESPONSE_BYTES} bytes (read {consumed})"
                    )
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip(" "))
                elif not line.strip() and data_lines:
                    events += 1
                    if events > MAX_SSE_EVENTS:
                        raise McpProtocolError(
                            f"MCP SSE response exceeded {MAX_SSE_EVENTS} events (read {events})"
                        )
                    content = "\n".join(data_lines)
                    data_lines.clear()
                    if not content.strip():
                        continue
                    message = json.loads(content)
                    if str(message.get("id")) == str(request_id):
                        return message, content
                    del message
            # Some legacy servers omit the final blank line before EOF.
            if data_lines:
                content = "\n".join(data_lines)
                message = json.loads(content)
                if str(message.get("id")) == str(request_id):
                    return message, content
            raise McpProtocolError(f"MCP SSE response did not contain JSON-RPC id {request_id}")
        chunks = []
        consumed = 0
        for chunk in response.iter_bytes():
            self._check_deadline()
            consumed += len(chunk)
            if consumed > MAX_RESPONSE_BYTES:
                raise McpProtocolError(
                    f"MCP response exceeded {MAX_RESPONSE_BYTES} bytes (read {consumed})"
                )
            chunks.append(chunk)
        self._check_deadline()
        content = b"".join(chunks).decode(encoding)
        return self._parse_response(content, content_type, request_id), content

    @staticmethod
    def _missing_response_error(status_code: int, detail: str) -> McpError:
        """An HTTP server error means the transport never reached a working MCP
        endpoint; only a 2xx/4xx body that is not valid JSON-RPC is a protocol fault."""
        if status_code == 0 or status_code >= 500:
            return McpTransportError(detail)
        return McpProtocolError(detail)

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

        timeout = self._remaining_timeout()
        self._check_deadline()
        status_code = 0
        try:
            with self.http.stream("POST", self.url, headers=headers, json=message, timeout=timeout) as response:
                self._check_deadline()
                status_code = response.status_code
                if response.status_code >= 500:
                    # A server error means the request never reached a working MCP
                    # endpoint, whatever body accompanied it. Check before parsing so
                    # an id mismatch or JSON error cannot mask the status.
                    raise self._missing_response_error(
                        response.status_code, f"MCP request failed: HTTP {response.status_code}"
                    )
                response.stream = _CheckedStream(response.stream, self._check_deadline)
                parsed, content = self._read_response(response, message.get("id"))
                return HttpResult(
                    status_code=response.status_code, headers=response.headers,
                    message=parsed, content_type=response.headers.get("content-type", ""),
                    raw_content=content,
                )
        except httpx.RequestError as exc:
            raise McpTransportError(f"MCP request failed: {exc}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise self._missing_response_error(
                status_code, f"MCP response is not valid JSON: {exc}"
            ) from exc

    def _discover_modern(self) -> bool:
        for _ in range(2):
            response = self._send(self._message(self._next_id(), "server/discover"))
            if response.message is None:
                raise self._missing_response_error(
                    response.status_code,
                    f"MCP modern discovery failed: HTTP {response.status_code} returned no JSON-RPC response",
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
            raise self._missing_response_error(
                response.status_code, "MCP legacy initialize failed"
            )
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
            raise self._missing_response_error(
                response.status_code,
                f"MCP {method} returned no JSON-RPC response (HTTP {response.status_code})",
            )
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
            timeout = min(self._remaining_timeout(), 10)
            if self.era == "legacy" and self.session_id and timeout > 0:
                try:
                    with self.http.stream(
                        "DELETE",
                        self.url,
                        headers={
                            "Mcp-Session-Id": self.session_id,
                            "MCP-Protocol-Version": self.protocol_version,
                        },
                        timeout=timeout,
                    ):
                        pass
                except httpx.RequestError:
                    pass
        finally:
            try:
                self.http.close()
            finally:
                if self._network is not None:
                    self._network.close()


def probe_tool_count(port: int, timeout: float) -> int:
    # Discovery, legacy negotiation, listing and session cleanup share one probe budget.
    deadline = time.monotonic() + timeout
    try:
        with McpClient(f"http://127.0.0.1:{port}/mcp", timeout=timeout, deadline=deadline) as client:
            count = len(client.request("tools/list").get("tools") or [])
        return count if time.monotonic() < deadline else -1
    except (McpProtocolError, McpTransportError):
        return -1
