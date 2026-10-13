# OMP native IDA support

## Scope

Provide a discoverable, portable OMP skill that uses the host's existing native IDA implementation. Keep the shared binary task route at `ida-reverse`, select the execution interface before applying transport-specific instructions, and document installation and dependency boundaries.

No new daemon, transport adapter, npm extension, host credential configuration, or model evaluation is required. The official Hex-Rays OMP extension is identified as a separate interface, not claimed as an implemented adapter.

## Scenario: OMP discovers the specialization

**Given** a source checkout or the complete specialization directory copied into a project's `.omp/skills/`
**When** OMP loads native project skills
**Then** `omp-ida-native` is discoverable from valid name/description metadata
**And** its setup and interface references resolve within the same portable directory.

## Scenario: Native-only OMP keeps the IDA route

**Given** OMP exposes the native IDA action schema, but no `idapro` MCP server is installed
**When** a native binary task enters the shared routing and IDA skill
**Then** the route accepts `omp_ida_native` as one supported capability alternative
**And** the skill enters the native specialization before applying MCP registration or `database` instructions.

`requires_capabilities` remains the set of jointly required capabilities. Optional `requires_any_capabilities` requires at least one listed alternative in addition to that set. `omp_ida_native` is a current-session native interface fact, not an executable path cached by the external tool index.

## Scenario: Existing MCP behavior remains available

**Given** the session exposes the project's `idapro` MCP interface
**When** the native interface is unavailable or the MCP workflow is selected
**Then** the existing HTTP MCP and Python CLI instructions still apply
**And** native `db` handles are never passed as MCP `database` or official instance handles.

## Scenario: Native database analysis is bounded and saved

**Given** the native database is open and its returned ID is known
**When** the agent reads views, performs batch Python queries, or makes permitted edits
**Then** it passes the explicit native ID, limits emitted results, reports partial outputs and errors, and saves and verifies edits
**And** it closes only databases whose lifecycle it owns.

## Scenario: Unsupported or missing backend is explicit

**Given** the native schema or worker dependency is unavailable
**When** the specialization is invoked
**Then** the agent reads setup guidance and diagnoses the actual interface
**And** it does not infer native availability from `omp`/IDA installation alone, start a separate MCP service for the native path, or apply native arguments to official extension tools.

## Verification boundary

Check discovery and reference loading against installed OMP without issuing a model prompt. Existing deterministic project checks cover route coherence. Actual IDA runtime verification and model-driven behavior must be reported separately; earlier legacy MCP verification does not establish native OMP behavior or a measured optimization gain.
