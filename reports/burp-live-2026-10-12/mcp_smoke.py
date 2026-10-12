import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path


BRIDGE = Path(__file__).resolve().parents[2] / "burp-mcp-full" / "mcp-bridge.js"
process = subprocess.Popen(
    ["node", str(BRIDGE)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.PIPE, text=True, encoding="utf-8",
    env={**os.environ, "BURP_MCP_HOST": "127.0.0.1", "BURP_MCP_PORT": "9876"},
)
responses = queue.Queue()
records = []
record_file = Path(__file__).with_name(f"mcp-smoke-records-{time.time_ns()}.json")


def read_responses():
    for line in process.stdout:
        responses.put(json.loads(line))


threading.Thread(target=read_responses, daemon=True).start()
try:
    calls = [
        ("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "burp-live-check", "version": "1"}}),
        ("tools/list", {}),
        ("tools/call", {"name": "burp_encode", "arguments": {"input": "probe", "type": "base64"}}),
        ("tools/call", {"name": "burp_burp_version", "arguments": {}}),
    ]
    for call_id, (method, params) in enumerate(calls, 1):
        if call_id == 2:
            process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        request = {"jsonrpc": "2.0", "id": call_id, "method": method, "params": params}
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        response = responses.get(timeout=15)
        records.append({"request": request, "response": response})
        assert response.get("id") == call_id and "result" in response, response
    tools = records[1]["response"]["result"]["tools"]
    for name in ("burp_intruder_attack", "burp_intruder_attack_async", "burp_intruder_with_options"):
        tool = next(tool for tool in tools if tool["name"] == name)
        assert tool["inputSchema"]["properties"]["pad_digits"]["maximum"] == 1024
    assert json.loads(records[2]["response"]["result"]["content"][0]["text"])["output"] == "cHJvYmU="
    version = json.loads(records[3]["response"]["result"]["content"][0]["text"])
    assert "error" not in version and {"name", "major", "minor", "build"} <= version.keys(), version
    print(json.dumps({"mcp_smoke": "passed", "tools": len(tools), "version": version, "records": str(record_file)}, ensure_ascii=False), flush=True)
finally:
    process.stdin.close()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    record_file.write_text(json.dumps({"cases": records, "bridge_exit": process.returncode, "stderr": process.stderr.read()}, ensure_ascii=False, indent=2), encoding="utf-8")
