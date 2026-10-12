# Static evidence to a dynamic observation plan

Implementation status: developed, not functionally tested. This workflow generates a plan and script; running the script is a separate action in the task's authorized target environment.

## Generate the plan

Use the snapshot or triage report produced by [the collector](triage.md). Select functions with concrete evidence and write the trigger input and expected observation. Provide the actual runtime module basename explicitly.

```console
python <skill-dir>/scripts/hook_plan.py --input triage.json --module sample.exe --rva 0x1000 --max-events 100 --duration 60 --output hook-plan.json
```

The generator validates source identity, bitness, supported architecture, unique targets, and `EA = image_base + RVA`. Explicit `--rva` values select known artifact targets. If omitted, the first `--max-targets` rows are selected and omitted rows are counted. No script or process is executed by the generator; existing output files are not overwritten.

The returned plan is `planned_not_run`, with unresolved identity and trigger preconditions. Its `frida_script` can be saved to a new file using OMP's JS `eval`:

```javascript
const fs = await import('node:fs');
const taskPlan = JSON.parse(fs.readFileSync('hook-plan.json', 'utf8'));
fs.writeFileSync('hooks.js', taskPlan.frida_script, { flag: 'wx' });
```

## Run and interpret separately

Before attachment, verify that the target module file matches the plan's source SHA-256. The generated script reports the expected source hash but does not independently verify the loaded module's bytes; `identity_verified` remains false.

Use the existing Frida workflow to attach in the task's authorized environment. The script converts RVA using `module.base.add(offset)`, checks module bounds and executable memory, and records entry arguments as pointer values and return values. It does not dereference pointers, change return values, patch code, or attach on its own.

Observe the prescribed trigger. A hit is an observation, not proof of the whole analysis; compare actual values with the recorded hypothesis. An absent hit remains unresolved. Event or time limits stop only this script's listeners; record any entry whose matching return was omitted by a limit.

Supported static/runtime architecture pairs are IDA x86/metapc with Frida ia32/x64 and IDA ARM64 with Frida arm64. ARM32/Thumb and other ISA states require a separate verified adapter; the generator rejects them.

## Sources

- [Frida JavaScript API](https://frida.re/docs/javascript-api/): `Process.getModuleByName`, `Process.findRangeByAddress`, `NativePointer.add`, `Interceptor.attach`, listener `detach`, and bounded timers.
- Existing shared dynamic guidance: `skills/reverse-engineering/tools-dynamic.md` and `skills/mobile-reverse/references/frida-objection-deep.md` when present in the full routing pack. The portable script does not depend on those files.
