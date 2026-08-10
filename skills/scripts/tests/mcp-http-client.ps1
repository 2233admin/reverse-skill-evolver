$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$clientScript = Join-Path $PSScriptRoot '..\lib\McpHttpClient.ps1'
. $clientScript

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

$json = '{"jsonrpc":"2.0","id":7,"result":{"ok":true}}'
$jsonResult = ConvertFrom-McpResponseContent -Content $json -ContentType 'application/json' -RequestId 7
Assert-True ($jsonResult.id -eq 7) 'JSON response id was not preserved.'
Assert-True ($jsonResult.result.ok -eq $true) 'JSON response result was not parsed.'

$sse = @'
event: message
data: {"jsonrpc":"2.0","method":"notifications/progress","params":{"progress":1}}

event: message
data: {"jsonrpc":"2.0","id":9,"result":{"value":"done"}}

'@
$sseResult = ConvertFrom-McpResponseContent -Content $sse -ContentType 'text/event-stream; charset=utf-8' -RequestId 9
Assert-True ($sseResult.id -eq 9) 'SSE parser did not select the matching JSON-RPC response.'
Assert-True ($sseResult.result.value -eq 'done') 'SSE response payload was not parsed.'

$missing = Get-McpPropertyValue -InputObject $sseResult -Name 'error'
Assert-True ($null -eq $missing) 'Missing JSON property should return null.'

$cliPath = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\reverse-skill.ps1')).Path
$cliCommand = Get-Command $cliPath
foreach ($parameter in @('Command', 'Url', 'Path', 'Tool', 'ArgumentsJson', 'Database', 'PreferredSessionId', 'Json')) {
    Assert-True ($cliCommand.Parameters.ContainsKey($parameter)) "CLI parameter is missing: $parameter"
}

Write-Output 'PASS: MCP JSON/SSE parsing and reverse CLI contract.'
