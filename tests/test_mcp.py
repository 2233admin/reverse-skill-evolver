import asyncio
import json
from typing import Any

import httpx
import pytest

from reverse_skill.errors import McpProtocolError
from reverse_skill.mcp import (
    MODERN_VERSION,
    McpClient,
    create_index_mcp_server,
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


def test_mcp2_index_tools_match_the_direct_index_api(tmp_path) -> None:
    mcp_server = pytest.importorskip("mcp.server")
    if not hasattr(mcp_server, "MCPServer"):
        pytest.skip("MCP 2.0 SDK is required for the in-memory adapter contract")
    from reverse_skill import index_api, index_build
    from reverse_skill.index_store import open_read_only

    (tmp_path / "guide.md").write_text("# Common\n\nbody\n", encoding="utf-8")
    index_build.build_apply(tmp_path)
    expected_status = index_api.index_status(tmp_path)
    expected_search = index_api.index_search(tmp_path, "Common", "hybrid", 5)
    index_path = tmp_path / ".reverse-skill" / "index" / "v1.sqlite3"
    connection = open_read_only(index_path)
    try:
        node_id = str(
            connection.execute(
                "SELECT n.node_id FROM nodes n "
                "JOIN documents d ON d.document_id = n.document_id "
                "ORDER BY d.relative_path, n.start_line, n.node_id"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    expected_tree = index_api.index_get_tree(tmp_path, node_id)
    expected_nodes = index_api.index_read_nodes(tmp_path, [node_id])

    async def exercise() -> tuple[
        set[str], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
    ]:
        from mcp import Client

        async with Client(create_index_mcp_server()) as client:
            tools = await client.list_tools()
            status = await client.call_tool(
                "index_status", {"root": str(tmp_path)}
            )
            search = await client.call_tool(
                "index_search",
                {
                    "root": str(tmp_path),
                    "query": "Common",
                    "mode": "hybrid",
                    "top_k": 5,
                },
            )
            tree = await client.call_tool(
                "index_get_tree",
                {"root": str(tmp_path), "node_id": node_id},
            )
            nodes = await client.call_tool(
                "index_read_nodes",
                {"root": str(tmp_path), "node_ids": [node_id]},
            )
            return (
                {tool.name for tool in tools.tools},
                dict(status.structured_content or {}),
                dict(search.structured_content or {}),
                dict(tree.structured_content or {}),
                dict(nodes.structured_content or {}),
            )

    names, status, search, tree, nodes = asyncio.run(exercise())
    assert names == {
        "index_status",
        "index_search",
        "index_get_tree",
        "index_read_nodes",
    }
    assert status == expected_status
    assert search == expected_search
    assert tree == expected_tree
    assert nodes == expected_nodes
