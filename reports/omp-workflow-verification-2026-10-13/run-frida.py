"""Verify emitted scripts only in self-spawned Python processes loading the owned DLL."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TEMP = ROOT / ".verification/frida-temp"
TEMP.mkdir(parents=True, exist_ok=True)
os.environ.update(TEMP=str(TEMP), TMP=str(TEMP), TMPDIR=str(TEMP))
import frida
import pefile
path = ROOT / ".omp/skills/omp-ida-native/scripts/hook_plan.py"
spec = importlib.util.spec_from_file_location("owned_hooks", path)
hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hooks)
snapshot = json.loads((HERE / "snapshot-v1.json").read_text(encoding="utf-8"))
dll = (HERE / "toy-v1.dll").resolve()
assert hashlib.sha256(dll.read_bytes()).hexdigest() == snapshot["source"]["sha256"]
target = next(row for row in snapshot["functions"] if row["name"] == "verify_license")
exports = pefile.PE(str(dll)).DIRECTORY_ENTRY_EXPORT.symbols
data_rva = next(symbol.address for symbol in exports if symbol.name == b"marker_reference")
child_code = """import ctypes,sys
library=ctypes.WinDLL(sys.argv[1])
library.verify_license.argtypes=[ctypes.c_int]
library.verify_license.restype=ctypes.c_int
print('ready',flush=True)
for line in sys.stdin:
    for count in range(3): library.verify_license(7)
    print('called',flush=True)
"""
receipt = {"frida_version": frida.__version__, "input_sha256": snapshot["source"]["sha256"], "model_calls": 0, "cases": []}
for case in ("aslr_event_limit", "not_hit_time_limit", "wrong_module", "wrong_bitness", "wrong_architecture", "rva_outside", "not_executable"):
    artifact = copy.deepcopy(snapshot)
    name = "missing-owned-module.dll" if case == "wrong_module" else dll.name
    if case == "wrong_bitness":
        artifact["source"].update(bitness=32, image_base="0x10000000")
        for row in artifact["functions"]:
            row["ea"] = hex(0x10000000 + int(row["rva"], 16))
    elif case == "wrong_architecture":
        artifact["source"]["architecture"] = "arm64"
    elif case in ("rva_outside", "not_executable"):
        rva = 0x10000000 if case == "rva_outside" else data_rva
        artifact["functions"] = [{"name": "deliberately_invalid_target", "rva": hex(rva), "ea": hex(int(artifact["source"]["image_base"],16)+rva)}]
    selected = artifact["functions"][0]["rva"] if case in ("rva_outside", "not_executable") else target["rva"]
    plan = hooks.generate_hook_plan(artifact, name, [selected], max_events=2, duration_seconds=1, arg_count=1)
    child = subprocess.Popen([sys.executable, "-u", "-c", child_code, str(dll)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    session = None
    records = []
    other_records = []
    stopped = threading.Event()
    other_survived = threading.Event()
    observer = None
    try:
        assert child.stdout.readline().strip() == "ready"
        assert child.poll() is None
        session = frida.get_local_device().attach(child.pid)
        if case == "aslr_event_limit":
            observer = session.create_script(f"Interceptor.attach(Process.getModuleByName({json.dumps(dll.name)}).base.add(ptr({json.dumps(target['rva'])})), {{onEnter() {{send({{other_listener:true}});}}}});")
            def other_message(value, data):
                other_records.append(value)
                if len(other_records) >= 4:
                    other_survived.set()
            observer.on("message", other_message)
            observer.load()
        script = session.create_script(plan["frida_script"])
        def message(value, data):
            records.append(value)
            if value.get("payload", {}).get("type") == "stopped": stopped.set()
        script.on("message", message)
        script.load()
        if case == "aslr_event_limit":
            child.stdin.write("trigger\n"); child.stdin.flush()
            assert child.stdout.readline().strip() == "called"
        assert stopped.wait(5), records
        payloads = [record["payload"] for record in records if record["type"] == "send"]
        assert not any(record["type"] == "error" for record in records), records
        stop = next(row for row in payloads if row["type"] == "stopped")
        if case == "aslr_event_limit":
            installed = next(row for row in payloads if row["type"] == "installed")
            entered = next(row for row in payloads if row["type"] == "enter")
            assert int(entered["address"],16) == int(installed["base"],16) + int(target["rva"],16)
            assert int(installed["base"],16) != int(snapshot["source"]["image_base"],16)
            assert stop["reason"] == "event_limit" and stop["events"] == 2
            child.stdin.write("after_stop\n"); child.stdin.flush()
            assert child.stdout.readline().strip() == "called"
            assert other_survived.wait(3), other_records
            assert sum(row["type"] in ("enter","leave") for row in payloads) == 2
        elif case == "not_hit_time_limit":
            assert stop["reason"] == "time_limit" and stop["events"] == 0
        else:
            assert stop["reason"] == "setup_failed" and stop["events"] == 0
            assert any(row["type"] == "error" for row in payloads)
        receipt["cases"].append({"case": case, "pid": child.pid, "source_fault_injected": case not in ("aslr_event_limit", "not_hit_time_limit"), "plan_status": plan["status"], "events": payloads, "other_listener_events": len(other_records)})
        (HERE / f"hook-plan-{case}.json").write_bytes((json.dumps(plan, indent=2)+"\n").encode("utf-8"))
        print(f"real Frida owned fixture: {case} PASS", flush=True)
    finally:
        if session is not None:
            session.detach()
        child.stdin.close()
        child.wait(timeout=5)
(HERE / "frida-verification.json").write_bytes((json.dumps(receipt, indent=2)+"\n").encode("utf-8"))
