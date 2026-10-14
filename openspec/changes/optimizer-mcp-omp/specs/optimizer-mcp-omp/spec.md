## ADDED Requirements

### Requirement: Recover from completed malformed stdio frames
The bridge SHALL report JSON-RPC -32700 for each malformed completed line and SHALL parse the next completed line independently.

#### Scenario: A valid request follows a malformed line
- **WHEN** `]` is followed by legal initialize requests
- **THEN** the malformed line receives a parse error and every legal request receives its own response without a retained bad prefix

### Requirement: Bound MCP operations by the absolute deadline
The client SHALL share the caller's absolute deadline across sending, streamed response reads, negotiation, and session cleanup using cancellable network operations compatible with Python 3.10. The client SHALL close the response after the matching RPC event and SHALL NOT retry tool calls on timeout.

#### Scenario: An endless response remains active
- **WHEN** a server keeps sending incomplete JSON or unrelated SSE events
- **THEN** the operation fails at the deadline, releases its connection, and stops its owned event loop on close

#### Scenario: A matching event precedes an open stream
- **WHEN** a complete matching RPC response arrives before further events or a stalled stream
- **THEN** the request returns that response and closes its stream without waiting for EOF

### Requirement: Install one Burp HTTP callback
Concurrent first registration SHALL install exactly one callback, publishing active only after success. Rule clearing SHALL preserve one installed callback with no rules.

#### Scenario: Concurrent install then clear and configure
- **WHEN** two callers register while the first installation is blocked, then clear and reconfigure
- **THEN** one callback remains and each outgoing request receives one header edit and one replacement

### Requirement: Bound custom Python regex matching
Custom triage regexes SHALL run as one owned process batch with a finite deadline, accepted Python regex syntax, explicit timeout/failure, and termination/reaping on every exit. Native helpers SHALL remain in the original worker.

#### Scenario: A nested repetition consumes excessive CPU
- **WHEN** `^(a+)+$` scans a long near-match
- **THEN** triage raises a bounded failure, emits no successful report, and leaves no owned matching child running

### Requirement: Snapshot only executed signature fixtures
Replay SHALL validate all fixtures, freeze the original total, and snapshot/hash only the maxCases prefix before invoking callbacks.

#### Scenario: One of one thousand cases is selected
- **WHEN** maxCases is one
- **THEN** only one baseline and one callback input are cloned, total remains one thousand, and partial coverage never passes

#### Scenario: An unused fixture is invalid
- **WHEN** a fixture beyond maxCases has invalid JSON or a duplicate ID
- **THEN** validation fails before any replay callback
