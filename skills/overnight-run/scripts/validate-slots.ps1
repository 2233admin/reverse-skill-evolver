<#
.SYNOPSIS
    Smoke-check a FILLED copy of skills/overnight-run/OVERNIGHT.md before launching an
    unattended overnight run. Enforces the template's own claim: Phase 0 is a smoke test
    of slot fill quality -- a bad fill means fix the template copy, not the code.

.DESCRIPTION
    Checks, in order:
      1. No unreplaced {{...}} placeholders remain in the filled copy.
      2. The four "thinking" slots (DEADLINE, SPEC_FILE, ALLOWED_COMPONENTS, BANNED_PATTERNS)
         are present and non-empty.
      3. DEADLINE parses as an ISO-8601 timestamp (yyyy-MM-ddTHH:mm:ss with optional offset).

    PS 5.1 compatible. Exits 1 on any failure so it can gate a launcher.

.PARAMETER TemplatePath
    Path to the FILLED copy of OVERNIGHT.md (not the pristine template).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File skills/overnight-run/scripts/validate-slots.ps1 -TemplatePath .night-filled/OVERNIGHT.md
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TemplatePath
)
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $TemplatePath)) {
    Write-Host "[FAIL] template not found: $TemplatePath" -ForegroundColor Red
    exit 1
}
$raw = Get-Content -LiteralPath $TemplatePath -Raw -Encoding UTF8

$fail = $false

# 1. no unreplaced placeholders
$unresolved = [regex]::Matches($raw, '\{\{[A-Z_]+(?:\s*/\s*[A-Z_]+)*\}\}')
if ($unresolved.Count -gt 0) {
    $fail = $true
    $names = ($unresolved | ForEach-Object { $_.Value } | Sort-Object -Unique) -join ', '
    Write-Host "[FAIL] unresolved slot placeholders: $names" -ForegroundColor Red
} else {
    Write-Host '[OK] no unreplaced {{...}} placeholders' -ForegroundColor Green
}

# 2. required thinking slots present
$required = @('DEADLINE', 'SPEC_FILE', 'ALLOWED_COMPONENTS', 'BANNED_PATTERNS')
$missing = @()
foreach ($slot in $required) {
    if ($raw -notmatch [regex]::Escape($slot)) { $missing += $slot; continue }
    if ($raw -match ('\{\{' + [regex]::Escape($slot) + '\}\}')) { $missing += $slot }
}
if ($missing.Count -gt 0) {
    $fail = $true
    Write-Host "[FAIL] required thinking slots not filled: $($missing -join ', ')" -ForegroundColor Red
} else {
    Write-Host '[OK] required thinking slots present' -ForegroundColor Green
}

# 3. DEADLINE parses as ISO-8601. Locate by the slot-table row whose meaning column
#    says 绝对时间戳 (the {{DEADLINE}} marker is gone once filled).
$dl = [regex]::Match($raw, '(?m)^\|\s*`([^`]+)`\s*\|\s*[^|]*绝对时间戳')
if (-not $dl.Success) {
    $fail = $true
    Write-Host '[FAIL] DEADLINE slot row not found (first slot-table row must have a value and a 绝对时间戳 meaning)' -ForegroundColor Red
} else {
    $dlValue = $dl.Groups[1].Value.Trim()
    $parsed = [datetime]::MinValue
    $ok = $false
    # .NET TryParseExact(string, string[], ...) mis-handles 'zzz'; try each format singly.
    foreach ($fmt in @('yyyy-MM-ddTHH:mm:ss', 'yyyy-MM-ddTHH:mm:sszzz', 'yyyy-MM-ddTHH:mm:ssZ')) {
        if ([datetime]::TryParseExact(
            $dlValue, $fmt,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal,
            [ref]$parsed)) { $ok = $true; break }
    }
    if ($ok) {
        Write-Host "[OK] DEADLINE parses: $($parsed.ToString('s'))Z (UTC)" -ForegroundColor Green
        if ($parsed -lt [datetime]::UtcNow) { Write-Host '[WARN] DEADLINE is in the past' -ForegroundColor Yellow }
    } else {
        $fail = $true
        Write-Host "[FAIL] DEADLINE not parseable as ISO-8601: $dlValue" -ForegroundColor Red
    }
}

if ($fail) {
    Write-Host '[RESULT] slots NOT ready -- fix the filled copy, do not start the run' -ForegroundColor Red
    exit 1
}
Write-Host '[RESULT] slots ready' -ForegroundColor Green
exit 0
