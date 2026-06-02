param(
    [int]$Seconds = 0,
    [string]$Server = "http://localhost:8020",
    [string]$Token = "dev-internal-token",
    [string]$MeetingId = "demo-meeting",
    [string]$ChunksDir = ".\chunks",
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$DryRunSaveOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$agentRoot = Join-Path $repoRoot "native\desktop-agent"
$buildScript = Join-Path $PSScriptRoot "build_agent.ps1"
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

    New-Item -ItemType Directory -Force -Path $ChunksDir | Out-Null
    $resolvedChunks = Resolve-Path $ChunksDir

    $args = @(
        "--server", $Server,
        "--token", $Token,
        "--meeting-id", $MeetingId,
        "--save-chunks", $resolvedChunks
    )

    if ($Seconds -gt 0) {
        $args += @("--duration-sec", "$Seconds")
    }
    if ($DryRunSaveOnly) {
        $args += "--dry-run-save-only"
    }

    Write-Host "[agent] Play YouTube/browser/system audio for 10-20 seconds."
    if ($Seconds -gt 0) {
        Write-Host "[agent] Running for $Seconds second(s), then the agent should exit cleanly."
    } else {
        Write-Host "[agent] Stop the agent with Ctrl+C when enough audio has played."
    }
    Write-Host "[agent] WAV chunks will be saved to $resolvedChunks."

    & $exe @args

    $files = @(Get-ChildItem -Path $resolvedChunks -Filter "*.wav" -File -ErrorAction SilentlyContinue)
    if ($files.Count -eq 0) {
        Write-Warning "No WAV chunks were found in $resolvedChunks"
    } else {
        Write-Host "[PASS] Found $($files.Count) WAV chunk(s) in $resolvedChunks" -ForegroundColor Green
        Write-Host "[agent] Open one of them in a media player and confirm it contains system audio."
    }
} finally {
    Pop-Location
}
