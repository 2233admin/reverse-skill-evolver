#requires -Version 5

Set-StrictMode -Version Latest

function Test-McpProperty {
    param(
        $InputObject,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $InputObject) {
        return $false
    }
    if ($InputObject -is [System.Collections.IDictionary]) {
        return $InputObject.Contains($Name)
    }
    return $null -ne $InputObject.PSObject.Properties[$Name]
}

function Get-McpPropertyValue {
    param(
        $InputObject,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if (-not (Test-McpProperty -InputObject $InputObject -Name $Name)) {
        return $null
    }
    if ($InputObject -is [System.Collections.IDictionary]) {
        return $InputObject[$Name]
    }
    return $InputObject.PSObject.Properties[$Name].Value
}

function Set-McpPropertyValue {
    param(
        [Parameter(Mandatory = $true)]$InputObject,
        [Parameter(Mandatory = $true)][string]$Name,
        $Value
    )

    if ($InputObject -is [System.Collections.IDictionary]) {
        $InputObject[$Name] = $Value
    }
    elseif (Test-McpProperty -InputObject $InputObject -Name $Name) {
        $InputObject.PSObject.Properties[$Name].Value = $Value
    }
    else {
        $InputObject | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

function ConvertTo-McpObject {
    param($Value)

    if ($null -eq $Value) {
        return [pscustomobject]@{}
    }
    if ($Value -is [System.Collections.IDictionary]) {
        return [pscustomobject]$Value
    }
    return $Value
}

function Get-McpHeaderValue {
    param(
        $Headers,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $Headers) {
        return ''
    }

    $value = $null
    try {
        $value = $Headers[$Name]
    }
    catch {
        try {
            $value = $Headers.GetValues($Name)
        }
        catch {
            $value = $null
        }
    }

    if ($value -is [System.Array]) {
        return [string]$value[0]
    }
    return [string]$value
}

function ConvertTo-McpHeaderValue {
    param([AllowEmptyString()][string]$Value)

    $isPlain = $Value.Length -gt 0 -and
        $Value -match '^[\x09\x20-\x7e]+$' -and
        $Value -eq $Value.Trim() -and
        $Value -notmatch '^=\?base64\?.*\?=$'

    if ($isPlain) {
        return $Value
    }

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    return '=?base64?{0}?=' -f [Convert]::ToBase64String($bytes)
}

function ConvertTo-McpParameterHeaderValue {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][ValidateSet('string', 'integer', 'boolean')][string]$Type
    )

    switch ($Type) {
        'boolean' {
            if ($Value -isnot [bool]) {
                throw 'x-mcp-header boolean parameter value is not a Boolean.'
            }
            $text = if ([bool]$Value) { 'true' } else { 'false' }
        }
        'integer' {
            try { $number = [decimal]$Value } catch { throw 'x-mcp-header integer parameter value is not an integer.' }
            if ($number -ne [decimal]::Truncate($number) -or
                $number -lt -9007199254740991 -or $number -gt 9007199254740991) {
                throw 'x-mcp-header integer parameter value is outside the JavaScript safe integer range.'
            }
            $text = $number.ToString('0', [Globalization.CultureInfo]::InvariantCulture)
        }
        default {
            if ($Value -isnot [string]) {
                throw 'x-mcp-header string parameter value is not a String.'
            }
            $text = [string]$Value
        }
    }
    return ConvertTo-McpHeaderValue -Value $text
}

function Add-McpModernMetadata {
    param(
        [Parameter(Mandatory = $true)]$Client,
        $Params
    )

    $requestParams = ConvertTo-McpObject -Value $Params
    $meta = ConvertTo-McpObject -Value (Get-McpPropertyValue -InputObject $requestParams -Name '_meta')
    Set-McpPropertyValue -InputObject $meta -Name 'io.modelcontextprotocol/protocolVersion' -Value $Client.ProtocolVersion
    Set-McpPropertyValue -InputObject $meta -Name 'io.modelcontextprotocol/clientInfo' -Value $Client.ClientInfo
    Set-McpPropertyValue -InputObject $meta -Name 'io.modelcontextprotocol/clientCapabilities' -Value $Client.ClientCapabilities
    Set-McpPropertyValue -InputObject $requestParams -Name '_meta' -Value $meta
    return $requestParams
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
            if (Test-McpProperty -InputObject $message -Name 'id') {
                if ([string]$message.id -eq [string]$RequestId) {
                    return $message
                }
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

    $message = $Content | ConvertFrom-Json
    if ($null -ne $RequestId) {
        if (-not (Test-McpProperty -InputObject $message -Name 'id') -or
            [string]$message.id -ne [string]$RequestId) {
            throw "MCP JSON response did not contain JSON-RPC id $RequestId."
        }
    }
    return $message
}

function Get-McpHttpErrorResponse {
    param([Parameter(Mandatory = $true)]$ErrorRecord)

    $response = Get-McpPropertyValue -InputObject $ErrorRecord.Exception -Name 'Response'
    $statusCode = 0
    $headers = $null
    $content = ''

    if ($null -ne $response) {
        try { $statusCode = [int]$response.StatusCode } catch { $statusCode = 0 }
        try { $headers = $response.Headers } catch { $headers = $null }

        try {
            if ($null -ne $response.Content -and
                $null -ne $response.Content.PSObject.Methods['ReadAsStringAsync']) {
                $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            }
        }
        catch {
            $content = ''
        }

        if ([string]::IsNullOrWhiteSpace($content)) {
            try {
                $stream = $response.GetResponseStream()
                if ($null -ne $stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    try { $content = $reader.ReadToEnd() } finally { $reader.Dispose() }
                }
            }
            catch {
                $content = ''
            }
        }
    }

    $errorDetails = Get-McpPropertyValue -InputObject $ErrorRecord -Name 'ErrorDetails'
    $errorDetailsMessage = Get-McpPropertyValue -InputObject $errorDetails -Name 'Message'
    if ([string]::IsNullOrWhiteSpace($content) -and
        -not [string]::IsNullOrWhiteSpace([string]$errorDetailsMessage)) {
        $content = [string]$errorDetailsMessage
    }

    return [pscustomobject]@{
        StatusCode = $statusCode
        Headers    = $headers
        Content    = $content
    }
}

function New-McpRequestMessage {
    param(
        [Parameter(Mandatory = $true)]$Client,
        [Parameter(Mandatory = $true)]$Id,
        [Parameter(Mandatory = $true)][string]$Method,
        $Params = $null
    )

    $requestParams = ConvertTo-McpObject -Value $Params
    if ($Client.Era -eq 'modern') {
        $requestParams = Add-McpModernMetadata -Client $Client -Params $requestParams
    }

    return [pscustomobject]@{
        jsonrpc = '2.0'
        id      = $Id
        method  = $Method
        params  = $requestParams
    }
}

function Invoke-McpHttpMessage {
    param(
        [Parameter(Mandatory = $true)]$Client,
        [Parameter(Mandatory = $true)]$Message,
        [hashtable]$AdditionalHeaders,
        [int]$TimeoutSeconds = 120
    )

    $headers = @{
        Accept       = 'application/json, text/event-stream'
        'Mcp-Method' = [string]$Message.method
    }

    if ($Client.Era -eq 'legacy' -and -not [string]::IsNullOrWhiteSpace($Client.SessionId)) {
        $headers['Mcp-Session-Id'] = $Client.SessionId
    }
    if (-not [string]::IsNullOrWhiteSpace($Client.ProtocolVersion) -and
        ($Client.Era -eq 'modern' -or $Message.method -ne 'initialize')) {
        $headers['MCP-Protocol-Version'] = $Client.ProtocolVersion
    }

    $name = $null
    if ($null -ne $Message.params) {
        switch ($Message.method) {
            'tools/call' { $name = Get-McpPropertyValue -InputObject $Message.params -Name 'name' }
            'prompts/get' { $name = Get-McpPropertyValue -InputObject $Message.params -Name 'name' }
            'resources/read' { $name = Get-McpPropertyValue -InputObject $Message.params -Name 'uri' }
        }
    }
    if ($null -ne $name) {
        $headers['Mcp-Name'] = ConvertTo-McpHeaderValue -Value ([string]$name)
    }

    if ($null -ne $AdditionalHeaders) {
        foreach ($headerName in $AdditionalHeaders.Keys) {
            $headers[$headerName] = $AdditionalHeaders[$headerName]
        }
    }

    $requestId = if (Test-McpProperty -InputObject $Message -Name 'id') { $Message.id } else { $null }
    $body = $Message | ConvertTo-Json -Depth 50 -Compress
    $webResponse = $null

    try {
        $response = Invoke-WebRequest -Uri $Client.Url -Method Post -Headers $headers `
            -ContentType 'application/json' -Body $body -TimeoutSec $TimeoutSeconds -UseBasicParsing
        $webResponse = [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Headers    = $response.Headers
            Content    = [string]$response.Content
        }
    }
    catch {
        $webResponse = Get-McpHttpErrorResponse -ErrorRecord $_
        if ($webResponse.StatusCode -eq 0) {
            throw
        }
    }

    $contentType = Get-McpHeaderValue -Headers $webResponse.Headers -Name 'Content-Type'
    $responseMessage = $null
    $parseError = ''
    if ($null -ne $requestId -or $webResponse.StatusCode -notin @(202, 204)) {
        try {
            $responseMessage = ConvertFrom-McpResponseContent -Content $webResponse.Content `
                -ContentType $contentType -RequestId $requestId
        }
        catch {
            $parseError = $_.Exception.Message
        }
    }

    return [pscustomobject]@{
        StatusCode  = [int]$webResponse.StatusCode
        SessionId   = Get-McpHeaderValue -Headers $webResponse.Headers -Name 'Mcp-Session-Id'
        ContentType = $contentType
        Message     = $responseMessage
        RawContent  = $webResponse.Content
        ParseError  = $parseError
    }
}

function Select-McpModernProtocolVersion {
    param([object[]]$SupportedVersions)

    foreach ($version in @('2026-07-28')) {
        if ($version -in @($SupportedVersions)) {
            return $version
        }
    }
    return $null
}

function Get-NextMcpRequestId {
    param([Parameter(Mandatory = $true)]$Client)

    if ($Client.Era -eq 'modern') {
        return [guid]::NewGuid().ToString('N')
    }

    $requestId = $Client.NextRequestId
    $Client.NextRequestId++
    return $requestId
}

function Test-McpModernError {
    param($ErrorObject)

    $code = Get-McpPropertyValue -InputObject $ErrorObject -Name 'code'
    return $code -in @(-32020, -32021, -32022)
}

function Invoke-McpModernDiscovery {
    param(
        [Parameter(Mandatory = $true)]$Client,
        [int]$TimeoutSeconds = 30
    )

    for ($attempt = 0; $attempt -lt 2; $attempt++) {
        $message = New-McpRequestMessage -Client $Client -Id (Get-NextMcpRequestId -Client $Client) -Method 'server/discover'
        $response = Invoke-McpHttpMessage -Client $Client -Message $message -TimeoutSeconds $TimeoutSeconds
        if ($null -eq $response.Message) {
            $detail = if (-not [string]::IsNullOrWhiteSpace($response.ParseError)) {
                $response.ParseError
            }
            else {
                "HTTP $($response.StatusCode) returned no JSON-RPC response"
            }
            throw "MCP modern discovery failed: $detail"
        }

        $error = Get-McpPropertyValue -InputObject $response.Message -Name 'error'
        $result = Get-McpPropertyValue -InputObject $response.Message -Name 'result'

        if ($null -ne $result) {
            if ((Get-McpPropertyValue -InputObject $result -Name 'resultType') -ne 'complete') {
                return $false
            }
            $selected = Select-McpModernProtocolVersion -SupportedVersions @(Get-McpPropertyValue -InputObject $result -Name 'supportedVersions')
            if ([string]::IsNullOrWhiteSpace($selected)) {
                throw 'MCP modern server did not advertise a mutually supported protocol version.'
            }
            if ($selected -ne $Client.ProtocolVersion) {
                $Client.ProtocolVersion = $selected
                continue
            }

            $Client.Capabilities = Get-McpPropertyValue -InputObject $result -Name 'capabilities'
            $resultMeta = Get-McpPropertyValue -InputObject $result -Name '_meta'
            $Client.ServerInfo = Get-McpPropertyValue -InputObject $resultMeta -Name 'io.modelcontextprotocol/serverInfo'
            return $true
        }

        if ($null -ne $error -and (Test-McpModernError -ErrorObject $error)) {
            $code = Get-McpPropertyValue -InputObject $error -Name 'code'
            if ($code -eq -32022) {
                $data = Get-McpPropertyValue -InputObject $error -Name 'data'
                $selected = Select-McpModernProtocolVersion -SupportedVersions @(Get-McpPropertyValue -InputObject $data -Name 'supported')
                if (-not [string]::IsNullOrWhiteSpace($selected) -and $selected -ne $Client.ProtocolVersion) {
                    $Client.ProtocolVersion = $selected
                    continue
                }
            }
            $detail = $error | ConvertTo-Json -Depth 20 -Compress
            throw "MCP modern discovery failed: $detail"
        }

        return $false
    }

    throw 'MCP modern protocol negotiation did not converge.'
}

function Initialize-McpLegacyClient {
    param(
        [Parameter(Mandatory = $true)]$Client,
        [string]$ProtocolVersion = '2025-11-25',
        [int]$TimeoutSeconds = 30
    )

    $Client.Era = 'legacy'
    $Client.ProtocolVersion = ''
    $Client.SessionId = ''

    $initialize = [pscustomobject]@{
        jsonrpc = '2.0'
        id      = 1
        method  = 'initialize'
        params  = [pscustomobject]@{
            protocolVersion = $ProtocolVersion
            capabilities    = [pscustomobject]@{}
            clientInfo      = $Client.ClientInfo
        }
    }

    $response = Invoke-McpHttpMessage -Client $Client -Message $initialize -TimeoutSeconds $TimeoutSeconds
    $initializeError = Get-McpPropertyValue -InputObject $response.Message -Name 'error'
    if ($null -eq $response.Message -or $null -ne $initializeError) {
        $detail = if ($null -ne $response.Message) { $initializeError | ConvertTo-Json -Compress } else { 'empty response' }
        throw "MCP legacy initialize failed: $detail"
    }

    $negotiatedVersion = [string]$response.Message.result.protocolVersion
    $supportedVersions = @('2025-11-25', '2025-06-18', '2025-03-26')
    if ($negotiatedVersion -notin $supportedVersions) {
        throw "MCP server negotiated unsupported legacy protocol version: $negotiatedVersion"
    }

    $Client.ProtocolVersion = $negotiatedVersion
    $Client.SessionId = $response.SessionId
    $Client.ServerInfo = $response.Message.result.serverInfo
    $Client.Capabilities = $response.Message.result.capabilities

    $initialized = [pscustomobject]@{
        jsonrpc = '2.0'
        method  = 'notifications/initialized'
        params  = [pscustomobject]@{}
    }
    [void](Invoke-McpHttpMessage -Client $Client -Message $initialized -TimeoutSeconds $TimeoutSeconds)
}

function New-McpHttpClient {
    [CmdletBinding()]
    param(
        [string]$Url = 'http://127.0.0.1:13337/mcp',
        [string]$ProtocolVersion = '2026-07-28',
        [string]$LegacyProtocolVersion = '2025-11-25',
        [string]$ClientName = 'reverse-skill-cli',
        [string]$ClientVersion = '1.1.0',
        [int]$TimeoutSeconds = 30
    )

    if ($ProtocolVersion -notin @('2026-07-28')) {
        throw "Unsupported modern MCP protocol version: $ProtocolVersion"
    }

    $client = [pscustomobject]@{
        Url                    = $Url
        Era                    = 'modern'
        PreferredProtocolVersion = $ProtocolVersion
        ProtocolVersion        = $ProtocolVersion
        SessionId              = ''
        NextRequestId          = 2
        ClientInfo             = [pscustomobject]@{ name = $ClientName; version = $ClientVersion }
        ClientCapabilities     = [pscustomobject]@{}
        ServerInfo             = $null
        Capabilities           = $null
        ToolHeaders            = @{}
        ToolDefinitionsLoaded  = $false
    }

    if (-not (Invoke-McpModernDiscovery -Client $client -TimeoutSeconds $TimeoutSeconds)) {
        Initialize-McpLegacyClient -Client $client -ProtocolVersion $LegacyProtocolVersion -TimeoutSeconds $TimeoutSeconds
    }

    return $client
}

function Get-McpObjectEntries {
    param($InputObject)

    if ($null -eq $InputObject -or $InputObject -is [string] -or $InputObject.GetType().IsPrimitive) {
        return @()
    }
    if ($InputObject -is [System.Collections.IDictionary]) {
        return @($InputObject.GetEnumerator() | ForEach-Object {
            [pscustomobject]@{ Name = [string]$_.Key; Value = $_.Value }
        })
    }
    return @($InputObject.PSObject.Properties | ForEach-Object {
        [pscustomobject]@{ Name = $_.Name; Value = $_.Value }
    })
}

function Visit-McpSchemaNode {
    param(
        $Node,
        [string[]]$Path,
        [bool]$StaticReachable,
        [bool]$IsPropertySchema,
        [Parameter(Mandatory = $true)]$Annotations,
        [Parameter(Mandatory = $true)]$HeaderNames
    )

    if ($null -eq $Node -or $Node -is [string] -or $Node.GetType().IsPrimitive) {
        return
    }
    if ($Node -is [System.Collections.IEnumerable] -and
        -not ($Node -is [System.Collections.IDictionary]) -and
        -not ($Node -is [pscustomobject])) {
        foreach ($item in $Node) {
            Visit-McpSchemaNode -Node $item -Path $Path -StaticReachable $false -IsPropertySchema $false `
                -Annotations $Annotations -HeaderNames $HeaderNames
        }
        return
    }

    if (Test-McpProperty -InputObject $Node -Name 'x-mcp-header') {
        if (-not $StaticReachable -or -not $IsPropertySchema) {
            throw 'x-mcp-header is not on a statically reachable properties path.'
        }

        $rawHeaderName = Get-McpPropertyValue -InputObject $Node -Name 'x-mcp-header'
        if ($rawHeaderName -isnot [string]) {
            throw 'x-mcp-header name must be a string.'
        }
        $headerName = [string]$rawHeaderName
        if ([string]::IsNullOrEmpty($headerName) -or $headerName -notmatch "^[!#$%&'*+\-.^_``|~0-9A-Za-z]+$") {
            throw "Invalid x-mcp-header name: $headerName"
        }
        if (-not $HeaderNames.Add($headerName)) {
            throw "Duplicate x-mcp-header name: $headerName"
        }

        $type = [string](Get-McpPropertyValue -InputObject $Node -Name 'type')
        if ($type -notin @('string', 'integer', 'boolean')) {
            throw "x-mcp-header $headerName uses unsupported type: $type"
        }

        $Annotations.Add([pscustomobject]@{
            HeaderName = $headerName
            Path       = @($Path)
            Type       = $type
        })
    }

    foreach ($entry in (Get-McpObjectEntries -InputObject $Node)) {
        if ($entry.Name -in @('x-mcp-header')) {
            continue
        }
        if ($entry.Name -eq 'properties') {
            foreach ($property in (Get-McpObjectEntries -InputObject $entry.Value)) {
                Visit-McpSchemaNode -Node $property.Value -Path (@($Path) + $property.Name) `
                    -StaticReachable $StaticReachable -IsPropertySchema $StaticReachable `
                    -Annotations $Annotations -HeaderNames $HeaderNames
            }
            continue
        }

        Visit-McpSchemaNode -Node $entry.Value -Path $Path -StaticReachable $false -IsPropertySchema $false `
            -Annotations $Annotations -HeaderNames $HeaderNames
    }
}

function Get-McpToolHeaderAnnotations {
    param([Parameter(Mandatory = $true)]$Tool)

    $annotations = New-Object System.Collections.Generic.List[object]
    $headerNames = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $schema = Get-McpPropertyValue -InputObject $Tool -Name 'inputSchema'
    if ($null -ne $schema) {
        Visit-McpSchemaNode -Node $schema -Path @() -StaticReachable $true -IsPropertySchema $false `
            -Annotations $annotations -HeaderNames $headerNames
    }
    return $annotations.ToArray()
}

function Register-McpToolDefinitions {
    param(
        [Parameter(Mandatory = $true)]$Client,
        [Parameter(Mandatory = $true)]$Result
    )

    $validTools = New-Object System.Collections.Generic.List[object]
    foreach ($tool in @(Get-McpPropertyValue -InputObject $Result -Name 'tools')) {
        $name = [string](Get-McpPropertyValue -InputObject $tool -Name 'name')
        try {
            $Client.ToolHeaders[$name] = @(Get-McpToolHeaderAnnotations -Tool $tool)
            $validTools.Add($tool)
        }
        catch {
            Write-Warning "Ignoring invalid MCP tool definition '$name': $($_.Exception.Message)"
        }
    }
    Set-McpPropertyValue -InputObject $Result -Name 'tools' -Value $validTools.ToArray()
    $Client.ToolDefinitionsLoaded = $true
}

function Get-McpNestedValue {
    param(
        $InputObject,
        [string[]]$Path
    )

    $current = $InputObject
    foreach ($segment in $Path) {
        if (-not (Test-McpProperty -InputObject $current -Name $segment)) {
            return [pscustomobject]@{ Exists = $false; Value = $null }
        }
        $current = Get-McpPropertyValue -InputObject $current -Name $segment
    }
    return [pscustomobject]@{ Exists = $true; Value = $current }
}

function Get-McpToolRequestHeaders {
    param(
        [Parameter(Mandatory = $true)]$Client,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)]$Arguments
    )

    $headers = @{}
    if (-not $Client.ToolHeaders.ContainsKey($Name)) {
        return $headers
    }

    foreach ($annotation in @($Client.ToolHeaders[$Name])) {
        $extracted = Get-McpNestedValue -InputObject $Arguments -Path $annotation.Path
        if (-not $extracted.Exists -or $null -eq $extracted.Value) {
            continue
        }
        $headers['Mcp-Param-{0}' -f $annotation.HeaderName] = ConvertTo-McpParameterHeaderValue `
            -Value $extracted.Value -Type $annotation.Type
    }
    return $headers
}

function Invoke-McpRequest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Client,
        [Parameter(Mandatory = $true)][string]$Method,
        $Params = $null,
        [hashtable]$AdditionalHeaders,
        [int]$TimeoutSeconds = 120
    )

    $requestId = Get-NextMcpRequestId -Client $Client
    $message = New-McpRequestMessage -Client $Client -Id $requestId -Method $Method -Params $Params
    $response = Invoke-McpHttpMessage -Client $Client -Message $message `
        -AdditionalHeaders $AdditionalHeaders -TimeoutSeconds $TimeoutSeconds

    if ($null -eq $response.Message) {
        $detail = if (-not [string]::IsNullOrWhiteSpace($response.ParseError)) { $response.ParseError } else { "HTTP $($response.StatusCode) returned no JSON-RPC response" }
        throw "MCP $Method failed: $detail"
    }
    $requestError = Get-McpPropertyValue -InputObject $response.Message -Name 'error'
    if ($null -ne $requestError) {
        $detail = $requestError | ConvertTo-Json -Depth 20 -Compress
        throw "MCP $Method failed: $detail"
    }

    $result = $response.Message.result
    if ($Client.Era -eq 'modern' -and $Method -eq 'tools/list') {
        Register-McpToolDefinitions -Client $Client -Result $result
    }
    return $result
}

function Initialize-McpToolDefinitions {
    param(
        [Parameter(Mandatory = $true)]$Client,
        [Parameter(Mandatory = $true)][string]$ToolName,
        [int]$TimeoutSeconds = 120
    )

    if ($Client.Era -ne 'modern' -or $Client.ToolHeaders.ContainsKey($ToolName)) {
        return
    }

    $cursor = $null
    $seenCursors = @{}
    do {
        $params = if ($null -eq $cursor) { $null } else { [pscustomobject]@{ cursor = $cursor } }
        $result = Invoke-McpRequest -Client $Client -Method 'tools/list' -Params $params -TimeoutSeconds $TimeoutSeconds
        if ($Client.ToolHeaders.ContainsKey($ToolName)) {
            return
        }
        $cursor = Get-McpPropertyValue -InputObject $result -Name 'nextCursor'
        if (-not [string]::IsNullOrWhiteSpace([string]$cursor)) {
            if ($seenCursors.ContainsKey([string]$cursor)) {
                throw 'MCP tools/list returned a repeated pagination cursor.'
            }
            $seenCursors[[string]$cursor] = $true
        }
    } while (-not [string]::IsNullOrWhiteSpace([string]$cursor))

    throw "MCP tool '$ToolName' is unavailable or has an invalid x-mcp-header definition."
}

function Invoke-McpTool {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Client,
        [Parameter(Mandatory = $true)][string]$Name,
        $Arguments = $null,
        $InputResponses = $null,
        [AllowEmptyString()][string]$RequestState,
        [int]$TimeoutSeconds = 120
    )

    if ($Client.Era -ne 'modern' -and
        ($PSBoundParameters.ContainsKey('InputResponses') -or $PSBoundParameters.ContainsKey('RequestState'))) {
        throw 'MRTR inputResponses/requestState require MCP 2026-07-28 or newer.'
    }

    $toolArguments = ConvertTo-McpObject -Value $Arguments
    Initialize-McpToolDefinitions -Client $Client -ToolName $Name -TimeoutSeconds $TimeoutSeconds
    $toolParams = [pscustomobject]@{
        name      = $Name
        arguments = $toolArguments
    }
    if ($PSBoundParameters.ContainsKey('InputResponses')) {
        Set-McpPropertyValue -InputObject $toolParams -Name 'inputResponses' -Value $InputResponses
    }
    if ($PSBoundParameters.ContainsKey('RequestState')) {
        Set-McpPropertyValue -InputObject $toolParams -Name 'requestState' -Value $RequestState
    }

    $headers = if ($Client.Era -eq 'modern') {
        Get-McpToolRequestHeaders -Client $Client -Name $Name -Arguments $toolArguments
    }
    else {
        @{}
    }
    $result = Invoke-McpRequest -Client $Client -Method 'tools/call' -Params $toolParams `
        -AdditionalHeaders $headers -TimeoutSeconds $TimeoutSeconds

    if ((Get-McpPropertyValue -InputObject $result -Name 'resultType') -eq 'input_required') {
        return $result
    }
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

    if ($Client.Era -ne 'legacy' -or [string]::IsNullOrWhiteSpace($Client.SessionId)) {
        return
    }

    try {
        Invoke-WebRequest -Uri $Client.Url -Method Delete -Headers @{
            'Mcp-Session-Id'       = $Client.SessionId
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
