# Fixed signature comparison

Import the sibling [module](../scripts/signature-replay.mjs) through the actual OMP eval module-import interface. OMP supports persistent JavaScript and top-level await; inspect its current schema for module exposure rather than inventing a tool invocation. See the [OMP 18.8.9 eval source](https://github.com/can1357/oh-my-pi/blob/fa5ff4a3a977a28b93d025f4cf50f046e019f18c/packages/coding-agent/src/tools/eval.ts).

The export is `compareSignatures(fixtures, replay, { maxCases = 100 } = {})`. Each fixture has a unique nonblank string `id`, strict JSON `input`, and string `expected`. Inputs allow null, finite numbers, strings, booleans, dense arrays and plain objects; cycles, undefined, nonfinite numbers, accessors, symbols, hidden properties and nesting beyond 64 levels are rejected before any replay. No code is evaluated from fixtures.

Arrays must have the standard Array prototype; Proxy objects are rejected before property access. This prevents fixture-controlled iterator/proxy traps from executing during validation. Sync/async callbacks, mismatch/failure, baseline isolation and partial coverage were checked in Node/Bun; actual OMP 18.8.9 eval imported this module and retained definitions across separate cells. See [scoped evidence](https://github.com/2233admin/reverse-skill-evolver/blob/2233admin/repair-open-issues-15/reports/omp-workflow-verification-2026-10-13/README.md). These self-authored cases do not establish fresh server acceptance or production signing compatibility.

Resolve the absolute script path from the discovered skill's location, then import it in the JS runtime. For example, replace the local path before evaluating:

```js
const taskReplayUrl = await import('node:url');
const taskReplayModule = await import(taskReplayUrl.pathToFileURL('/absolute/path/to/omp-js-replay/scripts/signature-replay.mjs').href);
const compareSignatures = taskReplayModule.compareSignatures;
```

Use `pathToFileURL` for Windows drive paths as well. Load the private fixture JSON separately and supply the actual signing function; importing this module does not replay fixtures.

Before the first callback, the helper snapshots every fixture's ID, expected signature and cloned input, and calculates input hashes. Later changes to the caller's fixtures or array cannot change this run's baseline or coverage. `replay(clonedInput, { id })` is the current task's actual signing function and returns a string or Promise of a string. It receives another fresh structured clone; changes to that clone cannot change the internal baseline. The caller's objects are not frozen. Keep the callback local and deterministic. Freeze time, nonce and session dependencies explicitly instead of substituting fresh values.

For illustration only, this is a string-format demo, not a cryptographic signature or an observed result:

```js
const demoFixtures = [{
  id: 'demo-1', input: { value: 7, timestamp: 1700000000 },
  expected: 'demo:7:1700000000',
}];
const demoReplay = input => `demo:${input.value}:${input.timestamp}`;
const demoReport = await compareSignatures(demoFixtures, demoReplay);
```

The report uses `schema_version: 1`, `coverage`, `counts`, `passed`, and `cases`. Each case retains `id`, `input_sha256`, `matched`, `expected`, `actual`, and `error`. The digest is SHA-256 of UTF-8 `JSON.stringify(input)` in its current key order; it identifies those serialized bytes, not a universal canonical JSON form. Raw inputs are absent. Exceptions are recorded as `replay_failed` without their potentially sensitive message; a non-string return is `non_string_signature`. Mismatches and failures do not pass.

At most `maxCases` cases are replayed. The complete fixture array is validated first, including IDs outside that limit. A truncated suite has `coverage.complete: false` and `passed: false`; an empty suite also cannot pass. Summarize processed versus total and keep failures visible.

This helper adds no timeout or network transport. Run eval with a finite task budget. A callback that never settles can hold this comparison; cancelling eval must not be presented as guaranteed cancellation of callback I/O. Do not add automatic network retries to chase a matching signature.

Verification status: synthetic cases passed in Node/Bun and a real OMP 18.8.9 persistent eval session. That session explicitly imported the module with `--no-skills`; automatic skill discovery and third-party captures remain unverified.
