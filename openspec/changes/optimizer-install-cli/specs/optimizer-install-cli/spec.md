## ADDED Requirements

### Requirement: Installation failure remains recoverable
The installers SHALL report failed downloads, extraction, publication and required health checks as failures. Apktool SHALL publish only a complete validated staged JAR, keep an existing installation until publication, clean only owned temporary resources, and recover from previously incomplete JARs.

#### Scenario: Interrupted or invalid Apktool transfer
- **WHEN** a transfer writes partial bytes and fails, or a downloaded JAR fails validation
- **THEN** no partial final artifact is published and the next installation attempt can repair the installation
- **AND** unrelated files and an existing healthy installation are preserved

#### Scenario: Jadx installer fails in a conditional call
- **WHEN** lookup, download, extraction, copy, chmod or the version check fails
- **THEN** that capability is failed, other requested capabilities are still collected, and bootstrap returns nonzero

### Requirement: Local work stays bounded and equivalent
Refresh SHALL resolve the catalog once per invocation; fleet SHALL retain case-insensitive collision and output order semantics. Email, report and routing work SHALL eliminate overlapping suffix preparation while preserving existing results, ASR priority and default read-only plans.

#### Scenario: Repeated refresh observes new versions
- **WHEN** Markdown and JSON are rendered during one refresh
- **THEN** both use the same version snapshot
- **AND** a subsequent refresh obtains fresh versions

#### Scenario: Routing and report compatibility
- **WHEN** frozen route tasks, overrides, Unicode boundaries or intervening report headings are processed
- **THEN** complete plans and sections match baseline results and no authorization or capability verification is asserted

### Requirement: CLI startup preserves execution boundaries
Local CLI entrypoints SHALL defer HTTP client implementation imports, retain output-v1 compatibility and preserve cli._envelope and cli.emit. The launcher SHALL preserve isolation, signatures, directory ownership, caller cwd, Unicode argv and exit codes while checking health and dispatching in one child process.

#### Scenario: Dependency import fails before dispatch
- **WHEN** the bootstrap import block fails and produces its private failure signal
- **THEN** one dependency repair is allowed and a repeated import failure returns a runtime error envelope

#### Scenario: A dispatched command fails
- **WHEN** a command raises ImportError or exits with the bootstrap's internal signal code
- **THEN** it is executed once and is never retried or repaired based only on its exit status
