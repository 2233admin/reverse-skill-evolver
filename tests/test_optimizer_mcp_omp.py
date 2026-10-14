"""Issue #58 MCP deadline and streaming behavior; all servers are owned fixtures."""

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest

from reverse_skill import mcp
from reverse_skill.errors import McpTransportError


def discovery(body):
    return {"jsonrpc": "2.0", "id": body["id"], "result": {
        "resultType": "complete", "supportedVersions": [mcp.MODERN_VERSION],
    }}


def test_injected_drip_is_stopped_between_chunks_without_timing_assertions(monkeypatch):
    state = {"clock": 0, "chunks": 0, "closed": False}
    class Drip(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(20):
                state["clock"] += 1
                state["chunks"] += 1
                yield b" "
        def close(self):
            state["closed"] = True
    monkeypatch.setattr(mcp, "time", SimpleNamespace(monotonic=lambda: state["clock"]))
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=Drip(), headers={"content-type": "text/event-stream"}))
    with pytest.raises(McpTransportError, match="deadline exceeded"):
        mcp.McpClient("http://fixture/mcp", timeout=30, deadline=3, transport=transport)
    assert state["chunks"] == 3 and state["closed"]


def test_sse_completes_at_matching_event_and_never_reads_trailing_body():
    state = {"closed": False}
    class Events(httpx.SyncByteStream):
        def __init__(self, request_id):
            self.request_id = request_id
        def __iter__(self):
            yield b': heartbeat\r\ndata:\r\n\r\ndata: {"id":"other","result":{}}\r\n\r\n'
            event = json.dumps({"id": self.request_id, "result": {"value": "汉字"}}, ensure_ascii=False).encode()
            for byte in b"data: " + event + b"\r\n\r\n":
                yield bytes([byte])
            pytest.fail("read past matching RPC response")
        def close(self):
            state["closed"] = True
    def handle(request):
        body = json.loads(request.content)
        if body["method"] == "server/discover":
            return httpx.Response(200, json=discovery(body))
        return httpx.Response(200, stream=Events(body["id"]), headers={"content-type": "text/event-stream"})
    with mcp.McpClient("http://fixture/mcp", transport=httpx.MockTransport(handle)) as client:
        assert client.request("resources/list") == {"value": "汉字"}
    assert state["closed"]


def test_negotiation_and_notification_share_one_deadline(monkeypatch):
    state = {"clock": 0}
    methods = []
    def handle(request):
        body = json.loads(request.content)
        methods.append(body["method"])
        state["clock"] += 1
        result = {"protocolVersion": "2025-11-25"} if body["method"] == "initialize" else None
        return httpx.Response(200, json={"id": body.get("id"), "result": result})
    monkeypatch.setattr(mcp, "time", SimpleNamespace(monotonic=lambda: state["clock"]))
    with pytest.raises(McpTransportError, match="deadline exceeded"):
        mcp.McpClient("http://fixture/mcp", deadline=3, transport=httpx.MockTransport(handle))
    assert methods == ["server/discover", "initialize", "notifications/initialized"]


@contextmanager
def server_fixture(reply, *, stall_delete_headers=False):
    finished = threading.Event()
    delete_seen = threading.Event()
    finished.delete_seen = delete_seen
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                reply(self, body, finished)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def do_DELETE(self):
            delete_seen.set()
            if stall_delete_headers:
                finished.wait(5)
                return
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            # The DELETE response body must not hold cleanup open.
            finished.wait(5)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/mcp", finished
    finally:
        finished.set()
        server.shutdown()
        server.server_close()
        thread.join()


def send_json(handler, value, **headers):
    raw = json.dumps(value).encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    for name, value in headers.items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(raw)


def send_chunk(handler, raw):
    handler.wfile.write(f"{len(raw):x}\r\n".encode() + raw + b"\r\n")
    handler.wfile.flush()


@pytest.mark.parametrize("phase", ["headers", "json", "sse"])
def test_real_http_deadline_cancels_send_or_drip_and_never_retries_tool(phase):
    methods = []
    chunks = []
    def reply(handler, body, finished):
        methods.append(body["method"])
        if body["method"] == "server/discover":
            send_json(handler, discovery(body))
            return
        if phase == "headers":
            finished.wait(5)
            return
        handler.send_response(200)
        handler.send_header("Transfer-Encoding", "chunked")
        handler.send_header("Content-Type", "text/event-stream" if phase == "sse" else "application/json")
        handler.end_headers()
        raw = b'data: {"id":"other","result":{}}\n\n' if phase == "sse" else b" "
        for i in range(200):
            if finished.is_set():
                return
            send_chunk(handler, raw)
            chunks.append(i)
            finished.wait(0.01)
        send_chunk(handler, b"")
    with server_fixture(reply) as (url, finished):
        with mcp.McpClient(url) as client:
            network_thread = client._network.thread
            # Set the deadline after discovery so initialization overhead isn't a test threshold.
            client.deadline = client._network.deadline = time.monotonic() + 0.3
            client.tool_headers["fixture-side-effect"] = []
            with pytest.raises(McpTransportError):
                client.call_tool("fixture-side-effect")
            assert methods == ["server/discover", "tools/call"]
            assert len(chunks) < 200
            finished.set()
        assert client.http.is_closed and not network_thread.is_alive()


def test_real_sse_returns_before_eof_and_sync_api_works_inside_async_caller():
    import asyncio
    def reply(handler, body, finished):
        if body["method"] == "server/discover":
            send_json(handler, discovery(body))
            return
        handler.send_response(200)
        handler.send_header("Transfer-Encoding", "chunked")
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()
        raw = b"data: " + json.dumps({"id": body["id"], "result": {"ok": True}}).encode() + b"\n\n"
        send_chunk(handler, raw)
        finished.wait(5)
    with server_fixture(reply) as (url, finished):
        async def call_sync():
            with mcp.McpClient(url) as client:
                network_thread = client._network.thread
                assert client.request("resources/list") == {"ok": True}
                assert not finished.is_set()
            assert not network_thread.is_alive()
        asyncio.run(call_sync())


@pytest.mark.parametrize("stall_headers", [False, True], ids=["stalled-body", "stalled-headers"])
def test_legacy_delete_shares_deadline_and_closes_resources(stall_headers):
    methods = []
    def reply(handler, body, finished):
        methods.append(body["method"])
        if body["method"] == "initialize":
            send_json(handler, {"id": body["id"], "result": {"protocolVersion": "2025-11-25"}}, **{"Mcp-Session-Id": "fixture"})
        elif body["method"] == "notifications/initialized":
            handler.send_response(202)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
        else:
            send_json(handler, {"id": body["id"], "error": {"code": -32601}})
    with server_fixture(reply, stall_delete_headers=stall_headers) as (url, finished):
        with mcp.McpClient(url) as client:
            network_thread = client._network.thread
            client.deadline = client._network.deadline = time.monotonic() + 0.5
        assert not finished.is_set()
        assert finished.delete_seen.is_set()
        assert not network_thread.is_alive() and client.http.is_closed
        assert methods == ["server/discover", "initialize", "notifications/initialized"]
