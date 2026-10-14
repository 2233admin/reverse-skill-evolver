# Design decisions

## ER-01: synchronous API, cancellable network

Use the existing HTTPX dependency and Python 3.10 `asyncio.wait_for`, rather than adding a networking dependency. A private sync transport drives HTTPX async network I/O in an owned event loop; each send/read awaits only the remaining absolute budget. The loop is stopped and joined on client close. Explicitly injected synchronous transports retain their existing interface, with deadline checks between reads; arbitrary blocking Python test doubles cannot be forcibly interrupted safely. No tool-call retries are introduced. SSE selection ends when the matching RPC event is complete, so later events are outside that response's validation boundary. DELETE cleanup uses the same deadline and closes without consuming an unbounded body.

## SEC-03: one matching batch, native ownership unchanged

Use the Python standard library subprocess timeout and an adjacent JSON-only helper. Native enumeration, function lookup, and xrefs stay in the calling OMP worker. Only bounded plain text and regexes cross the process boundary; the child returns selected row indices and coverage. Built-in patterns keep their local safe path. Custom patterns use one fixed batch deadline; timeout is an explicit RuntimeError, with no successful partial artifact. The helper is resolved relative to the executing script, including documented exec loading, rather than the caller's current directory.

## CONC-001 and MEM fixes

A dedicated registration lock covers check, install, active publication, and rule changes/clearing; callbacks read a coherent rule snapshot. Registering fails without publishing active, so retry remains possible. Clearing leaves the single installed callback and removes its rules, as before. Stdio framing follows the MCP newline contract. Replay validates every fixture before selecting the prefix; frozen totals and selected baselines survive callback mutation.
