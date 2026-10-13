"""Generate a bounded Frida observation plan from a native IDA artifact."""

import argparse
import json
import re
import sys
from pathlib import Path


def generate_hook_plan(artifact, module_name, rvas=None, *, max_targets=10,
                       max_events=100, duration_seconds=60, arg_count=4):
    if (not isinstance(artifact, dict) or type(artifact.get("schema_version")) is not int
            or artifact["schema_version"] != 1):
        raise ValueError("Expected an IDA artifact with schema_version=1")
    if not isinstance(module_name, str) or not module_name.strip():
        raise ValueError("An explicit runtime module name is required")
    if module_name != module_name.strip() or any(ord(char) < 32 or char in "/\\" for char in module_name):
        raise ValueError("Use a module basename without control characters")
    for name, value, lower, upper in (
        ("max_targets", max_targets, 1, 100),
        ("max_events", max_events, 1, 10000),
        ("duration_seconds", duration_seconds, 1, 3600),
        ("arg_count", arg_count, 0, 8),
    ):
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f"{name} must be an integer in {lower}..{upper}")

    source = artifact.get("source")
    if not isinstance(source, dict):
        raise ValueError("Missing artifact source")
    sha = source.get("sha256")
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-fA-F]{64}", sha) is None:
        raise ValueError("source.sha256 must identify the static input")
    bitness = source.get("bitness")
    if type(bitness) is not int or bitness not in (32, 64):
        raise ValueError("source.bitness must be 32 or 64")
    architecture = source.get("architecture")
    if not isinstance(architecture, str):
        raise ValueError("source.architecture is required")
    runtime_arch = {
        ("metapc", 32): "ia32", ("metapc", 64): "x64",
        ("x86", 32): "ia32", ("x86", 64): "x64",
        ("arm", 64): "arm64", ("arm64", 64): "arm64",
        ("aarch64", 64): "arm64",
    }.get((architecture.lower(), bitness))
    if runtime_arch is None:
        raise ValueError("Supported targets are x86, x64 and ARM64; do not guess ISA state")
    image_base = _address(source.get("image_base"), "source.image_base", bitness)
    coverage = artifact.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("Artifact coverage is required")

    keys = [key for key in ("candidates", "functions") if key in artifact]
    if len(keys) != 1 or not isinstance(artifact[keys[0]], list):
        raise ValueError("Expected exactly one candidates or functions array")
    targets = {}
    for row in artifact[keys[0]]:
        if not isinstance(row, dict):
            raise ValueError("Target rows must be objects")
        rva = _address(row.get("rva"), "target.rva", bitness)
        ea = _address(row.get("ea"), "target.ea", bitness)
        if image_base + rva != ea or ea >= 1 << bitness:
            raise ValueError("Target EA must equal the static image base plus RVA")
        name = row.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Target name is required")
        if rva in targets:
            raise ValueError(f"Duplicate target RVA: {hex(rva)}")
        targets[rva] = {"name": name, "ea": hex(ea), "rva": hex(rva)}

    if rvas is None:
        selected = list(targets)[:max_targets]
    else:
        if not isinstance(rvas, list) or not rvas:
            raise ValueError("Requested RVAs must be a nonempty array")
        selected = [_address(rva, "requested RVA", bitness) for rva in rvas]
        if len(set(selected)) != len(selected) or len(selected) > max_targets:
            raise ValueError("Requested RVAs must be unique and within max_targets")
        if any(rva not in targets for rva in selected):
            raise ValueError("Requested RVA is absent from the input artifact")
    if not selected:
        raise ValueError("No targets; collect evidence before generating hooks")

    config = {
        "module": module_name,
        "architecture": runtime_arch,
        "pointer_size": bitness // 8,
        "source_sha256": sha.lower(),
        "targets": [targets[rva] for rva in selected],
        "max_events": max_events,
        "duration_ms": duration_seconds * 1000,
        "arg_count": arg_count,
    }
    return {
        "schema_version": 1,
        "status": "planned_not_run",
        "source": source,
        "source_coverage": coverage,
        "selection": {"available": len(targets), "selected": len(selected),
                      "omitted": len(targets) - len(selected)},
        "runtime": config,
        "preconditions": [
            {"check": "runtime module file matches source SHA-256", "status": "unverified"},
            {"check": "trigger input and expected argument/return observations recorded", "status": "unverified"},
        ],
        "frida_script": "const config = " + json.dumps(config, ensure_ascii=True, allow_nan=False) + ";\n" + _SCRIPT,
        "observations": [],
    }


def _address(value, label, bitness):
    if not isinstance(value, str) or re.fullmatch(r"0x[0-9a-fA-F]+", value) is None:
        raise ValueError(f"{label} must be a hexadecimal string")
    number = int(value, 16)
    if number >= 1 << bitness:
        raise ValueError(f"{label} exceeds the declared bitness")
    return number


_SCRIPT = """'use strict';
const listeners = [];
let active = true;
let events = 0;
let nextCall = 0;
let timer = null;

function stop(reason) {
  if (!active) return;
  active = false;
  if (timer !== null) clearTimeout(timer);
  for (const listener of listeners) {
    try { listener.detach(); }
    catch (error) { send({ type: 'detach_error', message: String(error) }); }
  }
  send({ type: 'stopped', reason, events });
}

function emit(event) {
  if (!active) return;
  events += 1;
  send(event);
  if (events >= config.max_events) stop('event_limit');
}

try {
  if (Process.pointerSize !== config.pointer_size || Process.arch !== config.architecture)
    throw new Error('Runtime architecture/bitness differs from the static artifact');
  const module = Process.getModuleByName(config.module);
  const checked = config.targets.map(target => {
    const offset = ptr(target.rva);
    if (offset.compare(ptr(module.size)) >= 0) throw new Error('RVA outside runtime module: ' + target.rva);
    const address = module.base.add(offset);
    const range = Process.findRangeByAddress(address);
    if (range === null || !range.protection.includes('x'))
      throw new Error('Target is not executable: ' + target.rva);
    return { target, address };
  });
  for (const { target, address } of checked) {
    listeners.push(Interceptor.attach(address, {
      onEnter(args) {
        if (!active) return;
        this.ompCallId = ++nextCall;
        const values = [];
        for (let i = 0; i < config.arg_count; i++) values.push(args[i].toString());
        emit({ type: 'enter', call_id: this.ompCallId, name: target.name, rva: target.rva,
               address: address.toString(), thread: this.threadId, args: values });
      },
      onLeave(value) {
        emit({ type: 'leave', call_id: this.ompCallId, name: target.name, rva: target.rva,
               thread: this.threadId, retval: value.toString() });
      }
    }));
  }
  send({ type: 'installed', module: module.name, path: module.path,
         base: module.base.toString(), source_sha256: config.source_sha256,
         identity_verified: false, targets: checked.length });
  timer = setTimeout(() => stop('time_limit'), config.duration_ms);
} catch (error) {
  send({ type: 'error', message: String(error) });
  stop('setup_failed');
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--module", required=True)
    parser.add_argument("--rva", action="append")
    parser.add_argument("--max-targets", type=int, default=10)
    parser.add_argument("--max-events", type=int, default=100)
    parser.add_argument("--duration", type=int, default=60, help="Maximum observation seconds")
    parser.add_argument("--arg-count", type=int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.input.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Input artifact exceeds 16 MiB")
        artifact = json.loads(args.input.read_text(encoding="utf-8"),
                              object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        plan = generate_hook_plan(
            artifact, args.module, args.rva, max_targets=args.max_targets,
            max_events=args.max_events, duration_seconds=args.duration, arg_count=args.arg_count,
        )
        encoded = json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output is None:
            sys.stdout.write(encoded)
        else:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(1, f"hook-plan: {error}\n")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


if __name__ == "__main__":
    main()
