#requires -Version 5

Set-StrictMode -Version Latest

function Get-McpPropertyValue {
    param(
        $InputObject,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $InputObject) {
        return $null
    }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Get-McpHeaderValue {
    param(
        [Parameter(Mandatory = $true)]$Headers,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $value = $Headers[$Name]
    if ($value -is [System.Array]) {
        return [string]$value[0]
    }
    return [string]$value
}

function ConvertFrom-McpSseContent {
    param(
        [Parameter(Mandatory = $true)][string]$Content,
        $RequestId
    )

    $messages = New-Object System.Collections.Generic.List[object]
    $dataLines = New-Object System.Collections.Generic.List[string]

    foreach ($line in ($Content -split "`r?`n")) {
        if ($line.StartsWith('data:')) {
            $data = $line.Substring(5)
            if ($data.StartsWith(' ')) {
                $data = $data.Substring(1)
            }
            $dataLines.Add($data)
            continue
        }

        if ([string]::IsNullOrWhiteSpace($line) -and $dataLines.Count -gt 0) {
            $messages.Add((($dataLines -join "`n") | ConvertFrom-Json))
            $dataLines.Clear()
        }
    }

    if ($dataLines.Count -gt 0) {
        $messages.Add((($dataLines -join "`n") | ConvertFrom-Json))
    }

    if ($messages.Count -eq 0) {
        throw 'MCP SSE response did not contain a data event.'
    }

    if ($null -ne $RequestId) {
        foreach ($message in $messages) {
            if ($null -ne $message.PSObject.Properties['id'] -and [string]$message.id -eq [string]$RequestId) {
                return $message
            }
        }
        throw "MCP SSE response did not contain JSON-RPC id $RequestId."
    }

    return $messages[$messages.Count - 1]
}

function ConvertFrom-McpResponseContent {
    param(
        [AllowEmptyString()][string]$Content,
        [string]$ContentType,
        $RequestId
    )

    if ([string]::IsNullOrWhiteSpace($Content)) {
        return $null
    }

    if ($ContentType -match '^text/event-stream') {
        return ConvertFrom-McpSseContent -Content $Content -RequestId $RequestId
    }

    return $Content | ConvertFrom-Json
}

function Invoke-McpHttpMessage {
    param(
        [Parameter(Mandatory = $true)]$Client,
        [Parameter(Mandatory = $true)]$Message,
        [int]$TimeoutSeconds = 120
    )

    $headers = @{
        Accept       = 'application/json, text/event-stream'
        'Mcp-Method' = [string]$Message.method
    }

    if (-not [string]::IsNullOrWhiteSpace($Client.SessionId)) {
        $headers['Mcp-Session-Id'] = $Client.SessionId
    }
    if (-not [string]::IsNullOrWhiteSpace($Client.ProtocolVersion) -and $Message.method -ne 'initialize') {
        $headers['MCP-Protocol-Version'] = $Client.ProtocolVersion
    }
    if ($Message.method -eq 'tools/call' -and $null -ne $Message.params -and
        $null -ne $Message.params.PSObject.Properties['name']) {
        $headers['Mcp-Name'] = [string]$Message.params.name
    }

    $requestId = $null
    if ($null -ne $Message.PSObject.Properties['id']) {
        $requestId = $Message.id
    }

    $body = $Message | ConvertTo-Json -Depth 50 -Compress
    $response = Invoke-WebRequest -Uri $Client.Url -Method Post -Headers $headers `
        -ContentType 'application/json' -Body $body -TimeoutSec $TimeoutSeconds -UseBasicParsing

    $responseMessage = $null
    if ($null -ne $requestId -or [int]$response.StatusCode -notin @(202, 204)) {
        $responseMessage = ConvertFrom-McpResponseContent -Content $response.Content `
            -ContentType (Get-McpHeaderValue -Headers $response.Headers -Name 'Content-Type') `
            -RequestId $requestId
    }

    [pscustomobject]@{
        StatusCode  = [int]$response.StatusCode
        SessionId   = Get-McpHeaderValue -Headers $response.Headers -Name 'Mcp-Session-Id'
        ContentType = Get-McpHeaderValue -Headers $response.Headers -Name 'Content-Type'
        Message     = $responseMessage
    }
}

function New-McpHttpClient {
    [CmdletBinding()]
    param(
        [string]$Url = 'http://127.0.0.1:13337/mcp',
        [string]$ProtocolVersion = '2025-11-25',
        [string]$ClientName = 'reverse-skill-cli',
        [string]$ClientVersion = '1.0.0',
        [int]$TimeoutSeconds = 30
    )

    $client = [pscustomobject]@{
        Url             = $Url
        ProtocolVersion = ''
        SessionId       = ''
        NextRequestId   = 2
        ServerInfo      = $null
        Capabilities    = $null
    }

    $initialize = [pscustomobject]@{
        jsonrpc = '2.0'
        id      = 1
        method  = 'initialize'
        params  = [pscustomobject]@{
            protocolVersion = $ProtocolVersion
            capabilities    = [pscustomobject]@{}
            clientInfo      = [pscustomobject]@{
                name    = $ClientName
                version = $ClientVersion
            }
        }
    }

    $response = Invoke-McpHttpMessage -Client $client -Message $initialize -TimeoutSeconds $TimeoutSeconds
    $initializeError = Get-McpPropertyValue -InputObject $response.Message -Name 'error'
    if ($null -eq $response.Message -or $null -ne $initializeError) {
        $detail = if ($null -ne $response.Message) { $initializeError | ConvertTo-Json -Compress } else { 'empty response' }
        throw "MCP initialize failed: $detail"
    }

    $negotiatedVersion = [string]$response.Message.result.protocolVersion
    $supportedVersions = @('2025-11-25', '2025-06-18', '2025-03-26')
    if ($negotiatedVersion -notin $supportedVersions) {
        throw "MCP server negotiated unsupported protocol version: $negotiatedVersion"
    }

    $client.ProtocolVersion = $negotiatedVersion
    $client.SessionId = $response.SessionId
    $client.ServerInfo = $response.Message.result.serverInfo
    $client.Capabilities = $response.Message.result.capabilities

    $initialized = [pscustomobject]@{
        jsonrpc = '2.0'
        method  = 'notifications/initialized'
        params  = [pscustomobject]@{}
    }
    [void](Invoke-McpHttpMessage -Client $client -Message $initialized -TimeoutSeconds $TimeoutSeconds)

    return $client
}

function Invoke-McpRequest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Client,
        [Parameter(Mandatory = $true)][string]$Method,
        $Params = $null,
        [int]$TimeoutSeconds = 120
    )

    $requestId = $Client.NextRequestId
    $Client.NextRequestId++
    $message = [pscustomobject]@{
        jsonrpc = '2.0'
        id      = $requestId
        method  = $Method
        params  = if ($null -eq $Params) { [pscustomobject]@{} } else { $Params }
    }

    $response = Invoke-McpHttpMessage -Client $Client -Message $message -TimeoutSeconds $TimeoutSeconds
    if ($null -eq $response.Message) {
        throw "MCP $Method returned an empty response."
    }
    $requestError = Get-McpPropertyValue -InputObject $response.Message -Name 'error'
    if ($null -ne $requestError) {
        $detail = $requestError | ConvertTo-Json -Depth 20 -Compress
        throw "MCP $Method failed: $detail"
    }
    return $response.Message.result
}

function Invoke-McpTool {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Client,
        [Parameter(Mandatory = $true)][string]$Name,
        $Arguments = $null,
        [int]$TimeoutSeconds = 120
    )

    $toolArguments = if ($null -eq $Arguments) { [pscustomobject]@{} } else { $Arguments }
    $result = Invoke-McpRequest -Client $Client -Method 'tools/call' -Params ([pscustomobject]@{
        name      = $Name
        arguments = $toolArguments
    }) -TimeoutSeconds $TimeoutSeconds

    if ((Get-McpPropertyValue -InputObject $result -Name 'isError') -eq $true) {
        $structured = Get-McpPropertyValue -InputObject $result -Name 'structuredContent'
        $detail = Get-McpPropertyValue -InputObject $structured -Name 'error'
        if ([string]::IsNullOrWhiteSpace([string]$detail)) {
            $content = @(Get-McpPropertyValue -InputObject $result -Name 'content')
            $detail = (@($content | ForEach-Object { Get-McpPropertyValue -InputObject $_ -Name 'text' }) -join '; ')
        }
        throw "MCP tool $Name failed: $detail"
    }

    return $result
}

function Close-McpHttpClient {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Client,
        [int]$TimeoutSeconds = 10
    )

    if ([string]::IsNullOrWhiteSpace($Client.SessionId)) {
        return
    }

    try {
        Invoke-WebRequest -Uri $Client.Url -Method Delete -Headers @{
            'Mcp-Session-Id'      = $Client.SessionId
            'MCP-Protocol-Version' = $Client.ProtocolVersion
        } -TimeoutSec $TimeoutSeconds -UseBasicParsing | Out-Null
    }
    catch {
        $statusCode = $null
        if ($null -ne $_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        if ($statusCode -notin @(405, 501)) {
            throw
        }
    }
    finally {
        $Client.SessionId = ''
    }
}
