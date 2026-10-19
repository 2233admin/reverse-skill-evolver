import json
import asyncio
import threading
import time
import warnings
import weakref
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import httpx
import pytest

from reverse_skill.errors import McpProtocolError, McpTransportError
from reverse_skill.mcp import (
    MAX_RESPONSE_BYTES,
    MAX_SSE_EVENTS,
    MODERN_VERSION,
    McpClient,
    _NetworkTransport,
    encode_header_value,
    encode_parameter_header,
)


def _json(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


def test_modern_discovery_headers_and_tool_parameter_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = _json(request)
        request_id = body["id"]
        if body["method"] == "server/discover":
            assert request.headers["MCP-Protocol-Version"] == MODERN_VERSION
            assert body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] == MODERN_VERSION
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "resultType": "complete",
                        "supportedVersions": [MODERN_VERSION],
                        "capabilities": {"tools": {}},
                        "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "mock", "version": "1"}},
                    },
                },
            )
        if body["method"] == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "ttlMs": 500,
                        "cacheScope": "private",
                        "tools": [
                            {
                                "name": "login",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "token": {"type": "string", "x-mcp-header": "Auth-Token"}
                                    },
                                },
                            },
                            {
                                "name": "invalid",
                                "inputSchema": {
                                    "type": "object",
                                    "x-mcp-header": "Not-Static",
                                },
                            },
                        ]
                    },
                },
            )
        assert body["method"] == "tools/call"
        assert request.headers["Mcp-Method"] == "tools/call"
        assert request.headers["Mcp-Name"] == "login"
        assert request.headers["Mcp-Param-Auth-Token"] == "secret"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"resultType": "complete", "structuredContent": {"success": True}},
            },
        )

    with McpClient("http://mock/mcp", transport=httpx.MockTransport(handler)) as client:
        listed = client.request("tools/list")
        assert [tool["name"] for tool in listed["tools"]] == ["login"]
        assert listed["ttlMs"] == 500
        assert listed["cacheScope"] == "private"
        result = client.call_tool("login", {"token": "secret"})

    assert result["structuredContent"]["success"] is True
    assert len({str(_json(request).get("id")) for request in seen}) == len(seen)


def test_modern_mrtr_round_trip_preserves_request_state() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        body = _json(request)
        request_id = body["id"]
        if body["method"] == "server/discover":
            result = {
                "resultType": "complete",
                "supportedVersions": [MODERN_VERSION],
                "capabilities": {"tools": {}},
            }
        elif body["method"] == "tools/list":
            result = {"tools": [{"name": "login", "inputSchema": {"type": "object"}}]}
        else:
            calls += 1
            if calls == 1:
                result = {"resultType": "input_required", "requestState": "opaque"}
            else:
                assert body["params"]["inputResponses"] == {"credentials": {"action": "accept"}}
                assert body["params"]["requestState"] == "opaque"
                result = {"resultType": "complete", "structuredContent": {"success": True}}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": request_id, "result": result})

    with McpClient("http://mock/mcp", transport=httpx.MockTransport(handler)) as client:
        first = client.call_tool("login")
        second = client.call_tool(
            "login",
            input_responses={"credentials": {"action": "accept"}},
            request_state=first["requestState"],
        )

    assert first["resultType"] == "input_required"
    assert second["structuredContent"]["success"] is True


def test_legacy_fallback_accepts_plain_notification_ack_and_rejects_mrtr() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(200)
        body = _json(request)
        method = body["method"]
        methods.append(method)
        if method == "server/discover":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32601, "message": "missing"}},
            )
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "legacy-session"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "legacy", "version": "1"},
                    },
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202, content=b"Accepted", headers={"Content-Type": "application/json"})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": []}})

    with McpClient("http://mock/mcp", transport=httpx.MockTransport(handler)) as client:
        assert client.era == "legacy"
        assert client.protocol_version == "2025-06-18"
        assert client.request("tools/list") == {"tools": []}
        with pytest.raises(McpProtocolError, match="MRTR"):
            client.call_tool("login", input_responses={})

    assert methods[:3] == ["server/discover", "initialize", "notifications/initialized"]


def test_header_encoding_uses_utf8_sentinel_when_plain_text_is_unsafe() -> None:
    assert encode_header_value("plain-token") == "plain-token"
    assert encode_header_value("Hello, 世界") == "=?base64?SGVsbG8sIOS4lueVjA==?="
    assert encode_header_value(" padded ") == "=?base64?IHBhZGRlZCA=?="
    assert encode_header_value("=?base64?literal?=") == "=?base64?PT9iYXNlNjQ/bGl0ZXJhbD89?="
    assert encode_parameter_header(9_007_199_254_740_991, "integer") == "9007199254740991"
    with pytest.raises(McpProtocolError, match="safe integer"):
        encode_parameter_header(9_007_199_254_740_992, "integer")


def test_json_and_sse_parsers_require_the_matching_response_id() -> None:
    json_message = McpClient._parse_response(
        '{"jsonrpc":"2.0","id":7,"result":{"ok":true}}',
        "application/json",
        7,
    )
    assert json_message is not None
    assert json_message["result"]["ok"] is True
    with pytest.raises(McpProtocolError, match="id 8"):
        McpClient._parse_response('{"jsonrpc":"2.0","id":7}', "application/json", 8)

    sse = (
        'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'
        'event: message\ndata: {"jsonrpc":"2.0","id":9,"result":{"value":"done"}}\n\n'
    )
    sse_message = McpClient._parse_response(sse, "text/event-stream", 9)
    assert sse_message is not None
    assert sse_message["result"]["value"] == "done"


@pytest.mark.parametrize(
    ("content_type", "scenario", "error"),
    [
        ("application/json", "matching", None),
        ("application/json", "unmatched", "MCP JSON response did not contain JSON-RPC id"),
        ("application/json", "non_object", "MCP JSON response is not an object"),
        ("text/event-stream", "matching", None),
        ("text/event-stream", "unmatched", "MCP SSE response did not contain JSON-RPC id"),
        ("text/event-stream", "malformed_before", "not valid JSON"),
        ("text/event-stream", "malformed_after", None),
        ("text/event-stream", "non_object_before", "no attribute 'get'"),
        ("text/event-stream", "non_object_before_malformed", "no attribute 'get'"),
        ("text/event-stream", "non_object_after", None),
    ],
)
def test_request_preserves_json_and_sse_response_validation(
    content_type: str, scenario: str, error: str | None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = _json(request)
        if body["method"] == "server/discover":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"resultType": "complete", "supportedVersions": [MODERN_VERSION]},
                },
            )
        matching = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"value": "done"}})
        unrelated = '{"jsonrpc":"2.0","id":"unrelated","result":{}}'
        content = matching
        if content_type == "application/json":
            if scenario == "unmatched":
                content = unrelated
            elif scenario == "non_object":
                content = "[]"
        else:
            duplicate = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"value": "later"}})
            events = [unrelated, matching, unrelated, duplicate]
            if scenario == "unmatched":
                events = [unrelated, unrelated]
            elif scenario == "malformed_before":
                events.insert(0, "{")
            elif scenario == "malformed_after":
                events.append("{")
            elif scenario == "non_object_before":
                events.insert(0, "[]")
            elif scenario == "non_object_before_malformed":
                events = ["[]", matching, "{"]
            elif scenario == "non_object_after":
                events.append("[]")
            content = "\n\n".join(f"event: message\ndata: {event}" for event in events)
        return httpx.Response(200, text=content, headers={"Content-Type": content_type})

    with McpClient("http://mock/mcp", transport=httpx.MockTransport(handler)) as client:
        if error is not None:
            expected_error = AttributeError if scenario.startswith("non_object_before") else McpProtocolError
            with pytest.raises(expected_error, match=error):
                client.request("resources/list")
        else:
            assert client.request("resources/list") == {"value": "done"}


def test_request_releases_unrelated_sse_events_before_decoding_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TrackedEvent(dict[str, Any]):
        pass

    event_refs: list[weakref.ReferenceType[TrackedEvent]] = []
    original_loads = json.loads

    def tracked_loads(content: str | bytes | bytearray, *args: Any, **kwargs: Any) -> Any:
        # Weak references observe event lifetime without keeping the events alive.
        assert all(reference() is None for reference in event_refs)
        decoded = original_loads(content, *args, **kwargs)
        if isinstance(decoded, dict) and decoded.get("id") in {"unrelated-before", "unrelated-after"}:
            event = TrackedEvent(decoded)
            event_refs.append(weakref.ref(event))
            return event
        return decoded

    def handler(request: httpx.Request) -> httpx.Response:
        body = _json(request)
        if body["method"] == "server/discover":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"resultType": "complete", "supportedVersions": [MODERN_VERSION]},
                },
            )
        matching = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"value": "done"}})
        events = [
            '{"jsonrpc":"2.0","id":"unrelated-before","result":{}}',
            matching,
            '{"jsonrpc":"2.0","id":"unrelated-after","result":{}}',
            '{"jsonrpc":"2.0","method":"notifications/progress","params":{}}',
        ]
        return httpx.Response(
            200,
            text="\n\n".join(f"data: {event}" for event in events),
            headers={"Content-Type": "text/event-stream"},
        )

    monkeypatch.setattr(json, "loads", tracked_loads)
    with McpClient("http://mock/mcp", transport=httpx.MockTransport(handler)) as client:
        assert client.request("resources/list") == {"value": "done"}
    # A matching event completes the RPC; later events are never decoded.
    assert len(event_refs) == 1
    assert all(reference() is None for reference in event_refs)


def test_invalid_modern_discovery_body_does_not_silently_fall_back() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>", headers={"Content-Type": "text/html"})

    # A 5xx means the request never reached a usable MCP endpoint, so this is a
    # transport failure rather than a protocol-negotiation fault. It must still
    # surface instead of silently falling back to legacy discovery.
    with pytest.raises(McpTransportError, match="HTTP 502"):
        McpClient("http://mock/mcp", transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "body",
    [
        '{"jsonrpc":"2.0","id":"other","error":{"code":-32603,"message":"boom"}}',
        '{"jsonrpc":"2.0","id":"other","result":{}}',
    ],
)
def test_server_error_with_well_formed_body_is_a_transport_failure(body: str) -> None:
    """A 5xx must be classified before the body is parsed.

    A syntactically valid JSON-RPC body previously took the protocol paths (id
    mismatch, or a reported error), masking the fact that the server never
    served a usable MCP endpoint.
    """
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text=body, headers={"Content-Type": "application/json"})

    with pytest.raises(McpTransportError, match="HTTP 502"):
        McpClient("http://mock/mcp", transport=httpx.MockTransport(handler))


def test_constructor_closes_http_client_when_discovery_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    error = McpProtocolError("discovery failed")

    class TrackingClient:
        closed = False

        def close(self) -> None:
            self.closed = True

    client = TrackingClient()

    def fail_discovery(_: McpClient) -> bool:
        raise error

    monkeypatch.setattr("reverse_skill.mcp.httpx.Client", lambda **_: client)
    monkeypatch.setattr(McpClient, "_discover_modern", fail_discovery)

    with pytest.raises(McpProtocolError) as raised:
        McpClient("http://mock/mcp")

    assert raised.value is error
    assert client.closed


class _StreamingServer:
    """A real socket server that streams forever without ever completing a response.

    The point is that no client-side deadline can save the reader: the server keeps
    handing out bytes as fast as the client asks for them, so only an explicit
    accumulation budget can stop it.
    """

    def __init__(self, content_type: str, chunk: bytes) -> None:
        self.content_type = content_type
        self.chunk = chunk
        self.sent = 0
        self.stop = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_: Any) -> None:
                pass

            def _discover(self, body: bytes) -> bool:
                try:
                    message = json.loads(body)
                except ValueError:
                    return False
                return message.get("method") == "server/discover"

            def _respond(self, discover: bool) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "application/json" if discover else outer.content_type)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                payload = (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": json.loads(self.rfile_body).get("id"),
                            "result": {"resultType": "complete", "supportedVersions": [MODERN_VERSION]},
                        }
                    ).encode("utf-8")
                    if discover
                    else None
                )
                if discover:
                    self.wfile.write(b"%x\r\n%s\r\n0\r\n\r\n" % (len(payload), payload))
                    self.wfile.flush()
                    return
                while not outer.stop.is_set():
                    try:
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(outer.chunk), outer.chunk))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                    outer.sent += len(outer.chunk)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile_body = self.rfile.read(length).decode("utf-8", "replace")
                self._respond(self._discover(self.rfile_body.encode("utf-8")))

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/mcp"

    def __enter__(self) -> "_StreamingServer":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_oversized_json_response_fails_instead_of_buffering_forever() -> None:
    """#15: a fast sender must hit the byte budget, not this process's memory limit."""
    with _StreamingServer("application/json", b"x" * (256 * 1024)) as server:
        with McpClient(server.url, timeout=30.0) as client:
            with pytest.raises(McpProtocolError) as raised:
                client.request("resources/list")

    message = str(raised.value)
    assert f"exceeded {MAX_RESPONSE_BYTES} bytes" in message
    # The report must name the observed size so an operator can tell how far past
    # the limit the peer went.
    read = int(message.rsplit("read ", 1)[1].rstrip(")"))
    assert MAX_RESPONSE_BYTES < read <= MAX_RESPONSE_BYTES + 256 * 1024
    assert server.sent < 4 * MAX_RESPONSE_BYTES, "the reader must stop pulling once capped"


def test_oversized_sse_event_stream_hits_the_byte_budget() -> None:
    """A single never-terminated SSE event is bounded by bytes, not by event count."""
    with _StreamingServer("text/event-stream", b"data: " + b"y" * (64 * 1024) + b"\n") as server:
        with McpClient(server.url, timeout=30.0) as client:
            with pytest.raises(McpProtocolError, match="exceeded") as raised:
                client.request("resources/list")

    assert str(MAX_RESPONSE_BYTES) in str(raised.value)


def test_sse_event_count_budget_fires_on_many_small_events() -> None:
    """Many small unrelated events exhaust the event budget before the byte budget."""
    event = b'data: {"jsonrpc":"2.0","id":"unrelated","result":{}}\n\n'
    with _StreamingServer("text/event-stream", event) as server:
        with McpClient(server.url, timeout=30.0) as client:
            with pytest.raises(McpProtocolError) as raised:
                client.request("resources/list")

    assert f"exceeded {MAX_SSE_EVENTS} events" in str(raised.value)
    # Small events must not have tripped the byte limit first, or this test would
    # pass for the wrong reason.
    assert len(event) * MAX_SSE_EVENTS < MAX_RESPONSE_BYTES


def test_normal_responses_still_read_within_the_budgets() -> None:
    """The budgets must not disturb ordinary responses."""
    payload = "z" * 400_000

    def handler(request: httpx.Request) -> httpx.Response:
        body = _json(request)
        if body["method"] == "server/discover":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"resultType": "complete", "supportedVersions": [MODERN_VERSION]},
                },
            )
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": body["id"], "result": {"value": payload}},
        )

    with McpClient("http://mock/mcp", transport=httpx.MockTransport(handler)) as client:
        assert client.request("resources/list") == {"value": payload}


def test_transport_close_drains_a_cancelled_in_flight_task() -> None:
    """#16: closing must not destroy a pending task.

    Cancelling only requests cancellation; the task still has to run its
    ``finally`` on a live loop. Measured before the fix: the task is destroyed
    while pending and its cleanup never runs.
    """
    transport = _NetworkTransport(None)
    finished: list[str] = []

    async def noop() -> None:
        return None

    async def suspended() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            finished.append("cleaned")

    transport.run(noop())  # starts the loop the way a real request would
    asyncio.run_coroutine_threadsafe(suspended(), transport.loop)
    time.sleep(0.2)
    assert transport.thread.is_alive()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        transport.close()

    messages = [str(w.message) for w in caught]
    assert not [m for m in messages if "never awaited" in m], messages
    assert not [m for m in messages if "destroyed but it is pending" in m], messages
    assert finished == ["cleaned"], "the cancelled task never ran its cleanup"
    assert transport.loop is None and transport.thread is None
    assert transport.closed is True


def test_closed_transport_is_not_resurrected_by_unwinding_cleanup() -> None:
    """#16: a retired transport must not be restarted.

    ``run()`` lazily creates the loop and thread, so calling it after ``close()``
    — as an unwinding ``_NetworkStream.close()`` does — previously left a live
    daemon loop and thread behind.
    """
    transport = _NetworkTransport(None)

    async def noop() -> None:
        return None

    transport.run(noop())
    transport.close()
    assert transport.loop is None and transport.thread is None

    async def closing() -> None:
        return None

    pending = closing()
    try:
        with pytest.raises(McpTransportError, match="closed"):
            transport.run(pending, cleanup=True)
    finally:
        pending.close()  # never submitted; close it so it is not left un-awaited

    assert transport.loop is None, "the transport was resurrected by a post-close run()"
    assert transport.thread is None


def test_stream_close_after_transport_close_is_a_no_op() -> None:
    """The unwind path: a stream closing after terminal shutdown must do nothing."""
    from reverse_skill.mcp import _NetworkStream

    transport = _NetworkTransport(None)

    async def noop() -> None:
        return None

    class FakeResponse:
        async def aclose(self) -> None:
            raise AssertionError("aclose must not run on a retired transport")

    transport.run(noop())
    stream = _NetworkStream(transport, FakeResponse())
    transport.close()
    stream.close()  # must not raise and must not restart the transport
    assert transport.loop is None and transport.thread is None
