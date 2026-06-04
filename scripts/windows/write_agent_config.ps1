param(
    [string]$BrainUrl = "http://localhost:8010",
    [string]$Token = "dev-internal-token",
    [Parameter(Mandatory = $true)]
    [string]$UserId,
    [Parameter(Mandatory = $true)]
    [string]$DeviceId,
    [Parameter(Mandatory = $true)]
    [string]$ClientSessionId,
    [string]$WorkspaceId = "",
    [string]$DisplayName = "Петя",
    [string]$MeetingId = "MTG-1",
    [ValidateSet("microphone", "mock")]
    [string]$CaptureMode = "microphone",
    [string]$InputDeviceId = "",
    [int]$ChunkMs = 3000,
    [string]$AsrProvider = "mock",
    [string[]]$MockPhrases = @(
        "Я подготовлю оплату до завтра 18:00",
        "Беру websocket на себя до пятницы",
        "Аня, проверь интеграцию с YouGile сегодня вечером"
    )
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function ConvertTo-TomlString([string]$Value) {
    $escaped = $Value.Replace("\", "\\").Replace('"', '\"')
    return '"' + $escaped + '"'
}

$configDir = Join-Path $env:LOCALAPPDATA "GreyCardinal\Daemon"
$configPath = Join-Path $configDir "config.toml"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

$phraseLines = $MockPhrases | ForEach-Object { "  $(ConvertTo-TomlString $_)" }
$content = @(
    "brain_api_url = $(ConvertTo-TomlString $BrainUrl)",
    "internal_token = $(ConvertTo-TomlString $Token)",
    "",
    "user_id = $(ConvertTo-TomlString $UserId)",
    "device_id = $(ConvertTo-TomlString $DeviceId)",
    "client_session_id = $(ConvertTo-TomlString $ClientSessionId)",
    "workspace_id = $(ConvertTo-TomlString $WorkspaceId)",
    "display_name = $(ConvertTo-TomlString $DisplayName)",
    "meeting_id = $(ConvertTo-TomlString $MeetingId)",
    "",
    "capture_mode = $(ConvertTo-TomlString $CaptureMode)",
    "input_device_id = $(ConvertTo-TomlString $InputDeviceId)",
    "chunk_ms = $ChunkMs",
    "asr_provider = $(ConvertTo-TomlString $AsrProvider)",
    "mock_phrases = [",
    ($phraseLines -join ",`r`n"),
    "]"
) -join "`r`n"

[System.IO.File]::WriteAllText(
    $configPath,
    $content,
    (New-Object System.Text.UTF8Encoding($false))
)
Write-Host "[PASS] Agent config written to $configPath" -ForegroundColor Green
Write-Output $configPath
