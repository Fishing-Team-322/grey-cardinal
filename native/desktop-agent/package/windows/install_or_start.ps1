param(
    [string]$BackendUrl = "https://fishingteam.su",
    [string]$AgentId = "agent-demo-001",
    [string]$MeetingId = "",
    [ValidateSet("microphone", "system_loopback")]
    [string]$CaptureMode = "microphone",
    [int]$DurationSec = 10,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$packageDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $packageDir "grey-cardinal-agent.exe"
if (-not (Test-Path $exe)) {
    throw "grey-cardinal-agent.exe was not found in $packageDir"
}

$configDir = Join-Path $env:LOCALAPPDATA "GreyCardinal\Daemon"
$configPath = Join-Path $configDir "config.toml"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

$content = @(
    "backend_url = ""$BackendUrl""",
    "agent_id = ""$AgentId""",
    "meeting_id = ""$MeetingId""",
    "capture_mode = ""$CaptureMode""",
    "duration_sec = $DurationSec",
    "output_dir = """"",
    "dry_run = $($DryRun.IsPresent.ToString().ToLowerInvariant())"
) -join "`r`n"

[System.IO.File]::WriteAllText($configPath, $content, [System.Text.UTF8Encoding]::new($false))

Write-Host "[gc-agent] Config written to $configPath"
Write-Host "[gc-agent] Starting capture. Use -DryRun to save WAV without upload."
& $exe --config $configPath
