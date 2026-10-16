## Why

Main contains the reviewed installation, ASR and 24 audit repairs, but its Python version still reports 1.1.2. The next testing release needs consistent metadata and installable artifacts from a precise source commit.

## What Changes

- Set Python metadata and CLI version to 1.2.0b2, and OpenCLI to the equivalent 1.2.0-beta.2.
- Update the changelog and testing instructions for the complete skill, wheel, source archive and existing Burp component.
- Build and verify a full source bundle with packages and SHA256 checksums from the release candidate.

## Impact

Release metadata and documentation change. Runtime behavior, dependencies, native tool configuration and the Burp component version remain as already reviewed. The release is a prerelease; actual public publishing is distinct from preparation and artifact verification.
