# v1.2.0-beta.2 testing guide

Python reports `1.2.0b2`; the GitHub release tag is `v1.2.0-beta.2`. This release includes the complete routing skill and the installation, indexing and MCP/OMP repairs. The Burp component retains its separate `2.0.0` version.

## Choose an installation

The full ZIP contains this repository's tracked skill resources and a `packages/` directory with the Python wheel, source archive, Burp JAR and checksums. A wheel alone installs the Python CLI; it does not install the skill modules or configure an AI client.

For a published tag, install the complete skill from another project directory:

```console
npx skills add https://github.com/2233admin/reverse-skill-evolver/tree/v1.2.0-beta.2 --skill reverse-skill-evolver --agent codex universal --yes --copy
```

`codex` selects Codex; `universal` installs the shared project directory that OMP discovers. Claude Code, Cursor and OpenCode use their documented `--agent` values. For an extracted ZIP before publication, replace the URL with the extracted directory's absolute path and run the installer from a separate consumer project.

From the installed root `SKILL.md`, resolve `<PACK_ROOT>` and run:

```console
python "<PACK_ROOT>/scripts/run.py" --version
python "<PACK_ROOT>/scripts/run.py" --help
python "<PACK_ROOT>/scripts/run.py" --json asr list
python "<PACK_ROOT>/scripts/run.py" --json route "Analyze an Android APK"
python "<PACK_ROOT>/scripts/run.py" --json gates all
```

Python 3.10+ is required. The first launcher call prepares a private runtime and installs the declared dependencies. Its setup output goes to stderr; `--json` command output remains on stdout. These commands do not start native services or analyze a real target.

## Install the wheel from the full ZIP

In PowerShell, enter the extracted bundle directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .\packages\reverse_skill_evolver_cli-1.2.0b2-py3-none-any.whl
.\.venv\Scripts\reverse-skill.exe --version
.\.venv\Scripts\reverse-skill.exe --help
.\.venv\Scripts\reverse-skill-swarm.exe --help
```

On POSIX, use `.venv/bin/python`, `.venv/bin/reverse-skill` and `.venv/bin/reverse-skill-swarm`. CLI version must be `1.2.0b2`. Repository gates require the complete source bundle; run them from its root.

## What to test

- ASR listing defaults to audited entries and excludes MCP servers. Check help for explicit task/kind filters before making a live registry request.
- Route suggestions keep ASR registry requests ahead of target keywords. Suggestions do not execute tools.
- Local indexing and IDA export import default to read-only planning. Use an authorized test directory and explicitly request apply when testing writes.
- Installation failures must report failure and permit a clean retry. Tool downloads and native tool availability are separate from skill installation.
- MCP timeout, malformed-frame recovery, Burp callback concurrency and OMP regex/replay behavior have synthetic regression evidence. Repeat native tests only in an environment you own and authorize.
- A swarm run requires a configured OMP model and an explicit logical call budget. Outputs remain advisory; do not treat partial coverage as a passed analysis.

## Burp and native tools

Load `packages/burp-mcp-full.jar` with Java 21+ and the documented Burp/MCP setup. IDA requires a licensed installation and the applicable native or MCP integration. Complete skill installation preserves the adjacent OMP helpers; it does not prove that OMP's native runtime or Burp's GUI is configured.

## Checksums and feedback

The release-level `SHA256SUMS.txt` covers the four downloadable artifacts. The full ZIP includes `packages/SHA256SUMS.txt` for its wheel, source archive and JAR. In PowerShell, use `Get-FileHash -Algorithm SHA256`; on POSIX use `sha256sum -c SHA256SUMS.txt`.

Report the release version, installation method, actual command and redacted logs in repository Issues. See `BETA-VALIDATION.md` for the exact verified scope and remaining environment limits.
