<#
.SYNOPSIS
    Scaffold the mechanical parts of Overnight Phase 0: .night/ five working files,
    the `night` integration branch, and a generated pre-commit hook that enforces
    baseline freeze + banned patterns + lint before any commit can land.

.DESCRIPTION
    Phase 0 of OVERNIGHT.md is the only phase whose steps are mechanical; this script
    automates steps 4-7. It does NOT fill the template and does NOT run the baseline
    commands -- the agent does that per contract. It only makes "physical" what the
    contract wants physical: BASELINE.md can no longer be committed after sealing, and
    banned patterns can no longer be committed at all.

    Generated hook: .git/hooks/pre-commit (sh wrapper) + .git/hooks/pre-commit.overnight.ps1.
    Both are git internals (untracked); the only tracked additions are the five files
    under .night/, exactly as the template allows.

.PARAMETER RepoRoot
    Git repo root. Defaults to `git rev-parse --show-toplevel` from the current directory.

.PARAMETER BaselineFile
    Repo-relative path of the sealed baseline file. Default: .night/BASELINE.md

.PARAMETER LintCmd
    {{LINT_CMD}} verbatim. Empty string disables the lint gate in the hook.

.PARAMETER BannedPatterns
    {{BANNED_PATTERNS}} entries. Each is matched as a regex over files under -TargetModule.

.PARAMETER TargetModule
    {{TARGET_MODULE}} path scope for the banned-pattern scan. Default: repo root.

.PARAMETER Force
    Overwrite an existing non-generated pre-commit hook.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File skills/overnight-run/scripts/new-overnight.ps1 -LintCmd "npx eslint ." -BannedPatterns @('reset --hard','force-push') -TargetModule skills
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$BaselineFile = '.night/BASELINE.md',
    [string]$LintCmd = '',
    [string[]]$BannedPatterns = @(),
    [string]$TargetModule = '.',
    [switch]$Force
)
$ErrorActionPreference = 'Stop'

# Accept both PowerShell array syntax (-BannedPatterns @('a','b')) and command-line
# comma strings (-BannedPatterns "a,b"); normalize into a flat array of non-empty entries.
$BannedPatterns = @($BannedPatterns | ForEach-Object { $_ -split ',' } | Where-Object { $_ -ne '' })

if (-not $RepoRoot) {
    $RepoRoot = git rev-parse --show-toplevel 2>$null
    if (-not $RepoRoot) { Write-Host '[FAIL] not inside a git repo' -ForegroundColor Red; exit 1 }
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

# working tree must be clean so BASE is well-defined, EXCEPT .night/ which is
# the run's own working area (may be pre-seeded, e.g. by triage/baseline prep).
$dirty = git -C $RepoRoot status --porcelain | Where-Object { $_ -notmatch '^\?\? \.night/' }
if ($dirty) {
    Write-Host '[FAIL] working tree is dirty; commit or stash before scaffolding (BASE must be clean)' -ForegroundColor Red
    $dirty | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    exit 1
}

# .night/ five files (template rule: only these five may be added)
$night = Join-Path $RepoRoot '.night'
New-Item -ItemType Directory -Force -Path $night | Out-Null
$now = [DateTime]::UtcNow.ToString('s') + 'Z'
$files = @{
    'BASELINE.md'    = "# Overnight Baseline`n`n> Sealed by new-overnight.ps1 at $now. Do not edit after sealing.`n`n## Test results`n`n## Bench medians`n`n## LOC`n"
    'REPORT.md'      = "# Overnight Report`n`n## 1. 三句话任务复述`n`n## 2. Phase 结局`n`n## 3. 基线封存证明`n`n## 4. 基线对照表`n`n## 5. FLAKY 集`n`n## 6. Phase 2 映射表 / QUARANTINE 摘要`n`n## 7. Phase 3 findings`n`n## 8. BLOCKERS 全文`n`n## 9. 最可能是错的决定`n"
    'BLOCKERS.md'    = "# Blockers`n`n> Phase: / Attempted: / Blocked by: / Needs: / State:`n"
    'QUARANTINE.md'  = "# Quarantined Tests`n`n> 测试名 / 断言了什么 / 规格依据 / 累计预算:`n"
    'FINDINGS.md'    = "# Findings (Phase 3)`n`n> Smell / Root type / Change / Why it dies / Fanout est. / Confidence / Status`n"
}
foreach ($name in $files.Keys) {
    $p = Join-Path $night $name
    if (-not (Test-Path -LiteralPath $p)) { Set-Content -LiteralPath $p -Value $files[$name] -Encoding UTF8 }
}

# night branch
$nightBranch = 'night'
$hasNight = git -C $RepoRoot rev-parse --verify --quiet "refs/heads/$nightBranch"
if (-not $hasNight) {
    git -C $RepoRoot checkout -b $nightBranch | Out-Null
    Write-Host "[OK] created branch $nightBranch from BASE $(git -C $RepoRoot rev-parse --short HEAD)"
} else {
    git -C $RepoRoot checkout $nightBranch | Out-Null
    Write-Host "[OK] using existing branch $nightBranch"
}

# generate hook (sh wrapper + ps1 logic). git may have a GLOBAL core.hooksPath
# (e.g. OMX/Codex sets one); we must not write into it. Instead point THIS repo's
# core.hooksPath at a repo-local directory so the overnight hook actually runs,
# without touching global config or other repos.
$gitDir = git -C $RepoRoot rev-parse --git-dir
if (-not [IO.Path]::IsPathRooted($gitDir)) { $gitDir = Join-Path $RepoRoot $gitDir }
# Read upstream hooks from GLOBAL/SYSTEM config only -- NOT local. On a re-run the
# local value is already our own .git/overnight-hooks; injecting that would make the
# generated hook chain itself (infinite recursion).
$existingHooksPath = git -C $RepoRoot config --global --get core.hooksPath
if (-not $existingHooksPath) { $existingHooksPath = git -C $RepoRoot config --system --get core.hooksPath }
if (-not $existingHooksPath) { $existingHooksPath = '' }
$hooksPathRel = '.git/overnight-hooks'
if ($existingHooksPath -and ($existingHooksPath -ne $hooksPathRel)) {
    Write-Host "[INFO] upstream core.hooksPath '$existingHooksPath' will be chained (global/system; local config untouched)" -ForegroundColor Yellow
}
git -C $RepoRoot config core.hooksPath $hooksPathRel
$hookDir = Join-Path $RepoRoot $hooksPathRel
New-Item -ItemType Directory -Force -Path $hookDir | Out-Null
$hook = Join-Path $hookDir 'pre-commit'
$hookPs = Join-Path $hookDir 'pre-commit.overnight.ps1'
if ((Test-Path -LiteralPath $hook) -and -not $Force -and -not (Select-String -LiteralPath $hook -Pattern 'overnight' -Quiet)) {
    Write-Host '[FAIL] pre-commit hook exists and is not generated by overnight-run; use -Force to overwrite' -ForegroundColor Red
    exit 1
}

$psContent = @'
# generated by new-overnight.ps1 -- do not edit
param()
$ErrorActionPreference = 'Stop'
$repo = git rev-parse --show-toplevel
# night-marker gate: only enforce inside a repo that actually has an overnight run.
# If core.hooksPath is shared (global override), this keeps other repos untouched.
if (-not (Test-Path -LiteralPath (Join-Path $repo '.night'))) { exit 0 }
# Chain upstream hooks from the ORIGINAL core.hooksPath (e.g. ECC secrets scan).
# We override repo-local core.hooksPath for the overnight hook, so we must re-run
# the upstream hook ourselves or security gates would silently disappear.
$upstreamHooks = '<UPSTREAM_HOOKS>'
$upstreamHook = ''
if ($upstreamHooks) {
    $upstreamHook = Join-Path $upstreamHooks 'pre-commit'
    if (-not (Test-Path -LiteralPath $upstreamHook)) { $upstreamHook = '' }
}
if ($upstreamHook -and (Test-Path -LiteralPath $upstreamHook)) {
    Write-Host '[HOOK] running upstream pre-commit (security gates)' -ForegroundColor Yellow
    # upstream hooks are typically bash scripts (e.g. ECC secrets scan); run via bash.
    $bashExe = (Get-Command bash -ErrorAction SilentlyContinue).Source
    if (-not $bashExe) { $bashExe = 'C:\Program Files\Git\bin\bash.exe' }
    if (Test-Path -LiteralPath $bashExe) {
        & $bashExe $upstreamHook
    } else {
        & $upstreamHook
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[HOOK] BLOCKED: upstream hook failed' -ForegroundColor Red
        exit 1
    }
}
$baseline = '<BASELINE>'
$target = '<TARGET>'
$patterns = @(<PATTERNS>)
$lint = '<LINT>'
$fail = $false

# 1. baseline freeze: allow the FIRST commit (sealing) of BASELINE.md, but reject any
#    subsequent modification of the already-tracked file. Unconditional rejection would
#    deadlock Phase 0 step 6 (the sealing commit itself could never land).
$staged = git -C $repo diff --cached --name-only
if ($staged -contains $baseline) {
    # "Already tracked" must mean "present in HEAD", not present in the index: on the
    # FIRST (sealing) commit the file is already staged (thus in the index) but not in
    # HEAD, and must be allowed. cat-file -t exits 0 if HEAD has the path; with
    # $ErrorActionPreference='Stop' native stderr becomes a terminating error, so wrap
    # in a try/catch and treat a thrown error as "not in HEAD".
    $baselineInHead = $false
    try {
        git -C $repo cat-file -t "HEAD:$baseline" 2>$null | Out-Null
        $baselineInHead = ($LASTEXITCODE -eq 0)
    } catch {
        $baselineInHead = $false
    }
    if ($baselineInHead) {
        Write-Host '[HOOK] BLOCKED: BASELINE.md is sealed (already in HEAD; no further edits allowed)' -ForegroundColor Red
        $fail = $true
    }
}

# 2. banned patterns over staged content
if ($patterns.Count -gt 0) {
    $hits = git -C $repo grep -n -E --cached -e ($patterns -join '|') -- $target 2>$null
    if ($LASTEXITCODE -eq 0 -and $hits) {
        Write-Host "[HOOK] BLOCKED: banned pattern match:`n$hits" -ForegroundColor Red
        $fail = $true
    }
}

if ($fail) { exit 1 }

# 3. lint
if ($lint) {
    Write-Host "[HOOK] running lint: $lint"
    cmd /c $lint
    if ($LASTEXITCODE -ne 0) { Write-Host '[HOOK] BLOCKED: lint failed' -ForegroundColor Red; exit 1 }
}
exit 0
'@
$patternsJoined = ($BannedPatterns | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ', '
$psContent = $psContent.Replace('<UPSTREAM_HOOKS>', $existingHooksPath).Replace('<BASELINE>', $BaselineFile).Replace('<TARGET>', $TargetModule).Replace('<PATTERNS>', $patternsJoined).Replace('<LINT>', $LintCmd.Replace("'", "''"))
Set-Content -LiteralPath $hookPs -Value $psContent -Encoding UTF8

$sh = @"
#!/bin/sh
# generated by new-overnight.ps1 -- do not edit
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$($hookPs -replace '/', '\')" "$@"
"@
Set-Content -LiteralPath $hook -Value $sh -Encoding ASCII
Write-Host '[OK] pre-commit hook installed (baseline freeze + banned patterns + lint)'
Write-Host '[DONE] .night/ scaffolded, night branch ready, hook installed'
