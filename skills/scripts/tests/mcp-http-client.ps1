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

function Assert-Equal {
    param(
        $Actual,
        $Expected,
        [string]$Message
    )
    if ([string]$Actual -ne [string]$Expected) {
        throw "$Message Expected '$Expected', got '$Actual'."
    }
}

function New-MockResponse {
    param(
        [int]$StatusCode = 200,
        $Payload = $null,
        [hashtable]$Headers = @{ 'Content-Type' = 'application/json' }
    )

    return [pscustomobject]@{
        StatusCode = $StatusCode
        Headers    = $Headers
        Content    = if ($null -eq $Payload) { '' } else { $Payload | ConvertTo-Json -Depth 50 -Compress }
    }
}

function Reset-McpMock {
    $script:MockMcpResponses = New-Object System.Collections.Queue
    $script:MockMcpCalls = New-Object System.Collections.Generic.List[object]
}

$json = '{"jsonrpc":"2.0","id":7,"result":{"ok":true}}'
$jsonResult = ConvertFrom-McpResponseContent -Content $json -ContentType 'application/json' -RequestId 7
Assert-True ($jsonResult.id -eq 7) 'JSON response id was not preserved.'
$mismatchedJsonRejected = $false
try {
    ConvertFrom-McpResponseContent -Content $json -ContentType 'application/json' -RequestId 8 | Out-Null
}
catch {
    $mismatchedJsonRejected = $true
}
Assert-True $mismatchedJsonRejected 'JSON parser accepted a mismatched response ID.'
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
Assert-True ($null -eq (Get-McpPropertyValue -InputObject $sseResult -Name 'error')) 'Missing JSON property should return null.'

Assert-Equal (ConvertTo-McpHeaderValue -Value 'us-west1') 'us-west1' 'Safe header changed.'
$unicodeHeader = 'Hello, ' + [char]0x4e16 + [char]0x754c
Assert-Equal (ConvertTo-McpHeaderValue -Value $unicodeHeader) '=?base64?SGVsbG8sIOS4lueVjA==?=' 'Unicode header was not encoded.'
Assert-Equal (ConvertTo-McpHeaderValue -Value ' padded ') '=?base64?IHBhZGRlZCA=?=' 'Padded header was not encoded.'
Assert-Equal (ConvertTo-McpHeaderValue -Value '=?base64?literal?=') '=?base64?PT9iYXNlNjQ/bGl0ZXJhbD89?=' 'Sentinel-like header was ambiguous.'
Assert-Equal (ConvertTo-McpParameterHeaderValue -Value 9007199254740991 -Type integer) '9007199254740991' 'Safe integer header changed.'
$unsafeIntegerRejected = $false
try { ConvertTo-McpParameterHeaderValue -Value 9007199254740992 -Type integer | Out-Null } catch { $unsafeIntegerRejected = $true }
Assert-True $unsafeIntegerRejected 'Unsafe integer header value was not rejected.'

# Shadow the cmdlet only inside this test process. The production functions resolve it dynamically.
function Invoke-WebRequest {
    [CmdletBinding()]
    param(
        [string]$Uri,
        [string]$Method,
        [hashtable]$Headers,
        [string]$ContentType,
        [string]$Body,
        [int]$TimeoutSec,
        [switch]$UseBasicParsing
    )

    $parsedBody = if ([string]::IsNullOrWhiteSpace($Body)) { $null } else { $Body | ConvertFrom-Json }
    $script:MockMcpCalls.Add([pscustomobject]@{
        Uri     = $Uri
        Method  = $Method
        Headers = $Headers
        Body    = $parsedBody
    })
    if ($script:MockMcpResponses.Count -eq 0) {
        throw 'No mock MCP response is queued.'
    }
    $mockResponse = $script:MockMcpResponses.Dequeue()
    $mockContentType = Get-McpHeaderValue -Headers $mockResponse.Headers -Name 'Content-Type'
    if ($null -ne $parsedBody -and (Test-McpProperty -InputObject $parsedBody -Name 'id') -and
        $mockContentType -match '^(application/json|text/event-stream)' -and
        -not [string]::IsNullOrWhiteSpace([string]$mockResponse.Content)) {
        $responseBody = $mockResponse.Content | ConvertFrom-Json
        if (Test-McpProperty -InputObject $responseBody -Name 'id') {
            Set-McpPropertyValue -InputObject $responseBody -Name 'id' -Value $parsedBody.id
            $mockResponse.Content = $responseBody | ConvertTo-Json -Depth 50 -Compress
        }
    }
    return $mockResponse
}

Reset-McpMock
$script:MockMcpResponses.Enqueue((New-MockResponse -Payload ([pscustomobject]@{
    jsonrpc = '2.0'
    id = 1
    result = [pscustomobject]@{
        resultType = 'complete'
        supportedVersions = @('2026-07-28')
        capabilities = [pscustomobject]@{ tools = [pscustomobject]@{} }
        _meta = [pscustomobject]@{ 'io.modelcontextprotocol/serverInfo' = [pscustomobject]@{ name = 'modern-test'; version = '1.0' } }
        ttlMs = 1000
        cacheScope = 'private'
    }
})))
$modernClient = New-McpHttpClient -Url 'http://mock/mcp'
Assert-Equal $modernClient.Era 'modern' 'Modern discovery selected the wrong era.'
Assert-Equal $modernClient.ProtocolVersion '2026-07-28' 'Modern discovery selected the wrong protocol.'
Assert-Equal $modernClient.ServerInfo.name 'modern-test' 'Modern server identity was not captured.'
Assert-Equal $script:MockMcpCalls.Count 1 'Modern discovery sent an unexpected handshake.'
$discoverCall = $script:MockMcpCalls[0]
Assert-Equal $discoverCall.Body.method 'server/discover' 'Modern client did not probe with server/discover.'
Assert-True ([string]$discoverCall.Body.id -match '^[0-9a-f]{32}$') 'Modern request ID is not a unique GUID.'
Assert-Equal $discoverCall.Headers['MCP-Protocol-Version'] '2026-07-28' 'Modern protocol header is missing.'
Assert-Equal $discoverCall.Headers['Mcp-Method'] 'server/discover' 'Mcp-Method header is missing.'
$discoverMeta = $discoverCall.Body.params._meta
Assert-Equal $discoverMeta.'io.modelcontextprotocol/protocolVersion' '2026-07-28' 'Request metadata version is missing.'
Assert-Equal $discoverMeta.'io.modelcontextprotocol/clientInfo'.name 'reverse-skill-cli' 'Client identity is missing.'
Assert-True ($null -ne $discoverMeta.'io.modelcontextprotocol/clientCapabilities') 'Client capabilities are missing.'

Reset-McpMock
$script:MockMcpResponses.Enqueue((New-MockResponse -StatusCode 400 -Payload ([pscustomobject]@{
    jsonrpc = '2.0'; id = 1; error = [pscustomobject]@{
        code = -32022; message = 'Unsupported protocol version'
        data = [pscustomobject]@{ supported = @('2026-07-28'); requested = '2099-01-01' }
    }
})))
$script:MockMcpResponses.Enqueue((New-MockResponse -Payload ([pscustomobject]@{
    jsonrpc = '2.0'; id = 1; result = [pscustomobject]@{
        resultType = 'complete'; supportedVersions = @('2026-07-28')
        capabilities = [pscustomobject]@{}
    }
})))
$retryClient = [pscustomobject]@{
    Url = 'http://mock/mcp'; Era = 'modern'; ProtocolVersion = '2099-01-01'; SessionId = ''
    ClientInfo = [pscustomobject]@{ name = 'test'; version = '1' }; ClientCapabilities = [pscustomobject]@{}
    ServerInfo = $null; Capabilities = $null
}
Assert-True (Invoke-McpModernDiscovery -Client $retryClient) 'Modern negotiation retry did not succeed.'
Assert-Equal $retryClient.ProtocolVersion '2026-07-28' 'UnsupportedProtocolVersion retry did not select a mutual version.'
Assert-Equal $script:MockMcpCalls.Count 2 'Modern version retry count is wrong.'

Reset-McpMock
$script:MockMcpResponses.Enqueue([pscustomobject]@{
    StatusCode = 502
    Headers = @{ 'Content-Type' = 'text/html' }
    Content = '<html>bad gateway</html>'
})
$invalidDiscoveryRejected = $false
$invalidDiscoveryMessage = ''
try {
    New-McpHttpClient -Url 'http://mock/mcp' | Out-Null
}
catch {
    $invalidDiscoveryMessage = $_.Exception.Message
    $invalidDiscoveryRejected = $_.Exception.Message -like 'MCP modern discovery failed:*'
}
Assert-True $invalidDiscoveryRejected "Invalid discovery response silently fell back to legacy. Actual error: $invalidDiscoveryMessage"

Reset-McpMock
$script:MockMcpResponses.Enqueue((New-MockResponse -Payload ([pscustomobject]@{
    jsonrpc = '2.0'; id = 1; error = [pscustomobject]@{ code = -32601; message = 'Method not found' }
})))
$script:MockMcpResponses.Enqueue((New-MockResponse -Headers @{
    'Content-Type' = 'application/json'; 'Mcp-Session-Id' = 'legacy-session'
} -Payload ([pscustomobject]@{
    jsonrpc = '2.0'; id = 1; result = [pscustomobject]@{
        protocolVersion = '2025-06-18'
        capabilities = [pscustomobject]@{ tools = [pscustomobject]@{} }
        serverInfo = [pscustomobject]@{ name = 'legacy-test'; version = '1.0' }
    }
})))
$script:MockMcpResponses.Enqueue((New-MockResponse -StatusCode 202))
$legacyClient = New-McpHttpClient -Url 'http://mock/mcp'
Assert-Equal $legacyClient.Era 'legacy' 'Unrecognized modern response did not fall back to legacy.'
Assert-Equal $legacyClient.ProtocolVersion '2025-06-18' 'Legacy negotiated version was not accepted.'
Assert-Equal $legacyClient.SessionId 'legacy-session' 'Legacy session ID was not captured.'
Assert-Equal (($script:MockMcpCalls | ForEach-Object { $_.Body.method }) -join ',') 'server/discover,initialize,notifications/initialized' 'Legacy lifecycle is incomplete.'
$legacyMrtrRejected = $false
try {
    Invoke-McpTool -Client $legacyClient -Name 'execute' -InputResponses ([pscustomobject]@{}) | Out-Null
}
catch {
    $legacyMrtrRejected = $_.Exception.Message -like '*require MCP 2026-07-28*'
}
Assert-True $legacyMrtrRejected 'Legacy client accepted modern MRTR parameters.'

Reset-McpMock
$script:MockMcpResponses.Enqueue((New-MockResponse -Payload ([pscustomobject]@{
    jsonrpc = '2.0'; id = 1; result = [pscustomobject]@{
        resultType = 'complete'; supportedVersions = @('2026-07-28')
        capabilities = [pscustomobject]@{ tools = [pscustomobject]@{} }
    }
})))
$toolClient = New-McpHttpClient -Url 'http://mock/mcp'
$validTool = [pscustomobject]@{
    name = 'execute'
    inputSchema = [pscustomobject]@{
        type = 'object'
        properties = [pscustomobject]@{
            region = [pscustomobject]@{ type = 'string'; 'x-mcp-header' = 'Region' }
            options = [pscustomobject]@{
                type = 'object'
                properties = [pscustomobject]@{
                    token = [pscustomobject]@{ type = 'string'; 'x-mcp-header' = 'Token' }
                }
            }
            greeting = [pscustomobject]@{ type = 'string'; 'x-mcp-header' = 'Greeting' }
            enabled = [pscustomobject]@{ type = 'boolean'; 'x-mcp-header' = 'Enabled' }
        }
    }
}
$invalidTool = [pscustomobject]@{
    name = 'invalid-number-header'
    inputSchema = [pscustomobject]@{
        type = 'object'
        properties = [pscustomobject]@{
            amount = [pscustomobject]@{ type = 'number'; 'x-mcp-header' = 'Amount' }
        }
    }
}
$invalidHeaderNameTool = [pscustomobject]@{
    name = 'invalid-header-name-type'
    inputSchema = [pscustomobject]@{
        type = 'object'
        properties = [pscustomobject]@{
            value = [pscustomobject]@{ type = 'string'; 'x-mcp-header' = 123 }
        }
    }
}
$script:MockMcpResponses.Enqueue((New-MockResponse -Payload ([pscustomobject]@{
    jsonrpc = '2.0'; id = 2; result = [pscustomobject]@{
        resultType = 'complete'; tools = @($validTool, $invalidTool, $invalidHeaderNameTool); ttlMs = 500; cacheScope = 'private'
    }
})))
$oldWarningPreference = $WarningPreference
$WarningPreference = 'SilentlyContinue'
try {
    $toolList = Invoke-McpRequest -Client $toolClient -Method 'tools/list'
}
finally {
    $WarningPreference = $oldWarningPreference
}
Assert-Equal @($toolList.tools).Count 1 'Invalid x-mcp-header tool was not filtered.'
Assert-Equal $toolList.ttlMs 500 'Cache TTL was discarded.'
Assert-Equal $toolList.cacheScope 'private' 'Cache scope was discarded.'

$script:MockMcpResponses.Enqueue((New-MockResponse -Payload ([pscustomobject]@{
    jsonrpc = '2.0'; id = 3; result = [pscustomobject]@{
        resultType = 'input_required'
        inputRequests = [pscustomobject]@{ credentials = [pscustomobject]@{ method = 'elicitation/create'; params = [pscustomobject]@{} } }
        requestState = 'opaque-state'
    }
})))
$arguments = [pscustomobject]@{
    region = 'us-west1'
    options = [pscustomobject]@{ token = ' padded ' }
    greeting = $unicodeHeader
    enabled = $true
}
$inputResponses = [pscustomobject]@{ credentials = [pscustomobject]@{ action = 'accept'; content = [pscustomobject]@{ token = 'secret' } } }
$inputRequired = Invoke-McpTool -Client $toolClient -Name 'execute' -Arguments $arguments `
    -InputResponses $inputResponses -RequestState 'opaque-retry' -TimeoutSeconds 30
Assert-Equal $inputRequired.resultType 'input_required' 'MRTR input_required result was not returned intact.'
$toolCall = $script:MockMcpCalls[$script:MockMcpCalls.Count - 1]
Assert-Equal $toolCall.Headers['Mcp-Name'] 'execute' 'Mcp-Name was not mirrored.'
Assert-Equal $toolCall.Headers['Mcp-Param-Region'] 'us-west1' 'Plain x-mcp-header value is wrong.'
Assert-Equal $toolCall.Headers['Mcp-Param-Token'] '=?base64?IHBhZGRlZCA=?=' 'Nested padded x-mcp-header value is wrong.'
Assert-Equal $toolCall.Headers['Mcp-Param-Greeting'] '=?base64?SGVsbG8sIOS4lueVjA==?=' 'Unicode x-mcp-header value is wrong.'
Assert-Equal $toolCall.Headers['Mcp-Param-Enabled'] 'true' 'Boolean x-mcp-header value is wrong.'
Assert-Equal $toolCall.Body.params.requestState 'opaque-retry' 'MRTR requestState was not echoed.'
Assert-Equal $toolCall.Body.params.inputResponses.credentials.action 'accept' 'MRTR inputResponses were not sent.'
$modernIdA = Get-NextMcpRequestId -Client $toolClient
$modernIdB = Get-NextMcpRequestId -Client $toolClient
Assert-True ([string]$modernIdA -ne [string]$modernIdB) 'Modern requests reused a JSON-RPC request ID.'

$cliPath = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\reverse-skill.ps1')).Path
$cliCommand = Get-Command $cliPath
foreach ($parameter in @('Command', 'Url', 'Path', 'Tool', 'ArgumentsJson', 'InputResponsesJson', 'RequestState', 'Database', 'PreferredSessionId', 'Json')) {
    Assert-True ($cliCommand.Parameters.ContainsKey($parameter)) "CLI parameter is missing: $parameter"
}

Write-Output 'PASS: dual-era MCP client, metadata headers, MRTR, JSON/SSE, and CLI contract.'
