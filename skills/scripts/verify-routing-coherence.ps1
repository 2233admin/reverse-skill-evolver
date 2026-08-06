<#
.SYNOPSIS
    Routing coherence gate for reverse-skill-evolver: routing.json must parse, every
    primary skill / fallback edge referenced by routing.json must exist, and every
    .md skill path referenced by routing.md tables must exist.

.DESCRIPTION
    Small standalone gate usable as the overnight dogfood TEST_CMD
    (skills/overnight-run/references/example-filled.md) and as a CI/review check.
    PS 5.1 compatible. Exits 1 listing all failures.

    Known non-path fallback targets (MCP service names) are skipped: jshookmcp,
    anything-analyzer.

.PARAMETER RepoRoot
    Repo root. Defaults to the directory two levels above this script
    (skills/scripts -> repo root).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File skills/scripts/verify-routing-coherence.ps1
#>
[CmdletBinding()]
param([string]$RepoRoot = '')
$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
$skillsRoot = Join-Path $RepoRoot 'skills'
$fail = New-Object System.Collections.Generic.List[string]
function Ok($m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Bad($m) { Write-Host "[FAIL] $m" -ForegroundColor Red; [void]$fail.Add($m) }

# --- routing.json parses ---
$routingJson = Join-Path $skillsRoot 'routing.json'
if (-not (Test-Path -LiteralPath $routingJson)) {
    Bad 'routing.json missing'
    Write-Host "[RESULT] FAIL ($($fail.Count))"
    exit 1
}
try {
    $routes = Get-Content -LiteralPath $routingJson -Raw -Encoding UTF8 | ConvertFrom-Json
    Ok 'routing.json parses'
} catch {
    Bad "routing.json parse error: $($_.Exception.Message)"
    Write-Host "[RESULT] FAIL ($($fail.Count))"
    exit 1
}

# --- routing.json primary + fallback paths exist ---
$nonPath = @('jshookmcp', 'anything-analyzer')
foreach ($r in $routes.macro_routes) {
    $p = Join-Path $skillsRoot $r.primary_skill
    if (Test-Path -LiteralPath $p) { Ok "route $($r.id): primary $($r.primary_skill)" }
    else { Bad "route $($r.id): primary missing $($r.primary_skill)" }
    foreach ($fe in @($r.fallback_edges)) {
        $goto = $fe.goto
        if ($nonPath -contains $goto) { continue }
        $gp = Join-Path $skillsRoot $goto
        if (Test-Path -LiteralPath $gp) { Ok "route $($r.id): fallback $goto" }
        else { Bad "route $($r.id): fallback missing $goto" }
    }
}

# --- routing.md referenced .md skill paths exist ---
$routingMd = Join-Path $skillsRoot 'routing.md'
if (-not (Test-Path -LiteralPath $routingMd)) {
    Bad 'routing.md missing'
} else {
    $md = Get-Content -LiteralPath $routingMd -Raw -Encoding UTF8
    # Lookbehind forbids starting mid-word (fixes backtick-wrapped paths matching from
    # the second character, e.g. 'radare2' -> 'adare2'). '*' refs (patterns*.md) are
    # intentionally not matched; they cannot be statically verified and are skipped.
    $refs = [regex]::Matches($md, '(?<![A-Za-z0-9])[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\.md') |
        ForEach-Object { $_.Value.Trim('`', ' ', '|', '*', '>', '<') } | Sort-Object -Unique
    foreach ($ref in $refs) {
        if ($ref -match '^\.\./') {
            $p = Join-Path $RepoRoot ($ref -replace '^\.\./', '')
        } else {
            $p = Join-Path $skillsRoot $ref
        }
        if (Test-Path -LiteralPath $p) {
            Ok "routing.md ref $ref"
            continue
        }
        # routing.md convention: when context already names the module
        # (e.g. `pentest-tools/SKILL.md` + `references/foo.md`), the
        # module prefix is omitted. Resolve bare references/ under any
        # skill's references/ before failing.
        if ($ref -match '^references/') {
            $leaf = Split-Path $ref -Leaf
            $found = Get-ChildItem -Path (Join-Path $skillsRoot '*') -Directory |
                ForEach-Object { Join-Path $_.FullName 'references' } |
                Where-Object { Test-Path (Join-Path $_ $leaf) } |
                Select-Object -First 1
            if ($found) {
                Ok "routing.md ref $ref (resolved under $(Split-Path (Split-Path $found -Parent) -Leaf))"
                continue
            }
        }
        # CTF sub-skills live under <repo-root>/CTF-Sandbox-Orchestrator/ and are
        # sometimes written bare in diagrams/pseudocode (e.g. routing.md line 241).
        $ctfP = Join-Path $RepoRoot (Join-Path 'CTF-Sandbox-Orchestrator' $ref)
        if (Test-Path -LiteralPath $ctfP) {
            Ok "routing.md ref $ref (resolved under CTF-Sandbox-Orchestrator/)"
            continue
        }
        Bad "routing.md ref missing $ref"
    }
}

if ($fail.Count -gt 0) {
    Write-Host "[RESULT] FAIL ($($fail.Count))"
    exit 1
}
Write-Host '[RESULT] routing coherence OK'
exit 0
