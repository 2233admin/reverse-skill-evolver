---
name: reverse-skill-evolver
description: Route authorized reverse-engineering, cybersecurity, and CTF tasks through the bundled skills and tool workflows. Use for APK/mobile, native binaries, JavaScript signatures, captured protocols, security assessments, Forefy ASR discovery, and bounded routing evolution.
---

# Reverse Skill Evolver

This directory is one complete installable skill. Its `skills/` and
`CTF-Sandbox-Orchestrator/` directories are bundled modules and resources.
Keep the directory intact when installing or updating it.

## Locate the package

Resolve paths from this `SKILL.md`, regardless of the caller's working directory:

- `<PACK_ROOT>`: the directory containing this file.
- `<SKILL_ROOT>`: `<PACK_ROOT>/skills`.
- CTF modules: `<PACK_ROOT>/CTF-Sandbox-Orchestrator`.

Read and execute referenced module files in this installed package. Their
relative paths depend on the bundled layout. Client registration is handled by
the skill installer; using this skill does not require global rule injection.

## Route the task

1. Use the current task's inputs, authorization, requested output, and success
   checks to select a route. For multi-step work, use
   `skills/evolution/goal.template.yaml` and `skills/evolution/SKILL.md`.
2. Read `skills/routing.json` and `skills/routing.md`, then the selected module's
   `SKILL.md`. An explicit Forefy ASR request enters
   `skills/asr-registry/SKILL.md`.
3. Consult `skills/ROUTER.md` for shared tool discovery, bootstrap, reporting,
   and journal conventions when those parts of the workflow apply. Tool
   availability and external service configuration are separate from installing
   this bundle.
4. Execute the requested workflow within the current authorization. Preserve
   evidence for results and route changes. Apply the evolution promotion gate
   to learned changes before treating them as stable routing knowledge.

## Python CLI

Use the bundled launcher whenever a module needs `reverse-skill`:

```text
python "<PACK_ROOT>/scripts/run.py" --help
python "<PACK_ROOT>/scripts/run.py" --json asr list
```

Python 3.10+ is required. On first use, the launcher creates a private runtime
in the user's cache and installs this package and its declared dependencies.
It preserves the caller's working directory, arguments, JSON output, and exit
code, with UTF-8 output and imports isolated from the caller's Python environment.
Setup diagnostics go to stderr. A setup failure stops before the CLI
operation runs and reports the actual error.

For PowerShell, shell, and module-local helpers, use their bundled paths as
documented by the selected module. Native tools and MCP services are prepared
only when the requested workflow needs them.
