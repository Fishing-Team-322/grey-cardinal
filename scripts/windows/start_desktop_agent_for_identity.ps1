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
    [int]$InputDeviceIndex = -1,
    [string]$InputDeviceName = "",
    [float]$MicGain = 1.0,
    [int]$DurationSec = 0,
    [string]$SaveChunks = "",
    [switch]$DryRun,
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$agentRoot = Join-Path $repoRoot "native\desktop-agent"
$buildScript = Join-Path $PSScriptRoot "build_agent.ps1"
$writeConfigScript = Join-Path $PSScriptRoot "write_agent_config.ps1"
$exeCandidates = @(
    (Join-Path $agentRoot "build\$Configuration\grey-cardinal-agent.exe"),
    (Join-Path $agentRoot "build\grey-cardinal-agent.exe")
)

Push-Location $repoRoot
try {
    & $buildScript -Configuration $Configuration

    $exe = $exeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) {
        throw "grey-cardinal-agent.exe was not found after build"
    }

    $configPath = & $writeConfigScript `
        -BrainUrl $BrainUrl `
        -Token $Token `
        -UserId $UserId `
        -DeviceId $DeviceId `
        -ClientSessionId $ClientSessionId `
        -WorkspaceId $WorkspaceId `
        -DisplayName $DisplayName `
        -MeetingId $MeetingId `
        -CaptureMode $CaptureMode `
        -InputDeviceId $InputDeviceId

    $args = @("--config", "$configPath")
    if ($InputDeviceId) {
        $args += @("--input-device-id", $InputDeviceId)
    }
    if ($InputDeviceIndex -ge 0) {
        $args += @("--input-device-index", "$InputDeviceIndex")
    }
    if ($InputDeviceName) {
        $args += @("--input-device-name", $InputDeviceName)
    }
    if ($MicGain -ne 1.0) {
        $args += @("--mic-gain", "$MicGain")
    }
    if ($DurationSec -gt 0) {
        $args += @("--duration-sec", "$DurationSec")
    }
    if (-not [string]::IsNullOrWhiteSpace($SaveChunks)) {
        New-Item -ItemType Directory -Force -Path $SaveChunks | Out-Null
        $args += @("--save-chunks", (Resolve-Path $SaveChunks))
    }
    if ($DryRun) {
        $args += "--dry-run"
    }

    Write-Host "[agent] Starting $exe"
    Write-Host "[agent] Config $configPath"
    Write-Host "[agent] Capture mode $CaptureMode, ASR mock"
    & $exe @args
} finally {
    Pop-Location
}
