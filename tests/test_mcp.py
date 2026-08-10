import json
from typing import Any

import httpx
import pytest

from reverse_skill.errors import McpProtocolError
from reverse_skill.mcp import (
    MODERN_VERSION,
    McpClient,
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


def test_invalid_modern_discovery_body_does_not_silently_fall_back() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>", headers={"Content-Type": "text/html"})

    with pytest.raises(McpProtocolError, match="not valid JSON"):
        McpClient("http://mock/mcp", transport=httpx.MockTransport(handler))
