param(
    [int]$Seconds = 5,
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$agentRoot = Join-Path $repoRoot "native\desktop-agent"
$buildScript = Join-Path $PSScriptRoot "build_agent.ps1"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$baseDir = "C:\Temp\GreyCardinal\mic-diagnose\$timestamp"
$exeCandidates = @(
    (Join-Path $agentRoot "build\$Configuration\grey-cardinal-agent.exe"),
    (Join-Path $agentRoot "build\grey-cardinal-agent.exe")
)

function Write-Step([string]$Msg) { Write-Host "[diagnose] $Msg" }
function Write-Pass([string]$Msg) { Write-Host "[GOOD] $Msg" -ForegroundColor Green }
function Write-Warn([string]$Msg) { Write-Host "[LOW ] $Msg" -ForegroundColor Yellow }
function Write-Fail([string]$Msg) { Write-Host "[FAIL] $Msg" -ForegroundColor Red }

Push-Location $repoRoot
try {
    Write-Step "Building agent..."
    & $buildScript -Configuration $Configuration

    $exe = $exeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) {
        throw "grey-cardinal-agent.exe was not found after build"
    }

    # Parse device list from agent
    $deviceLines = & $exe --list-input-devices 2>&1
    $devices = @()
    $currentDevice = $null
    foreach ($line in $deviceLines) {
        if ($line -match '^\s*\[(\d+)\]\s+(.+)') {
            if ($currentDevice) { $devices += $currentDevice }
            $currentDevice = @{ Index = [int]$Matches[1]; Label = $Matches[2].Trim(); Id = ""; Role = "" }
        } elseif ($line -match 'id:\s*(.+)' -and $currentDevice) {
            $currentDevice.Id = $Matches[1].Trim()
        } elseif ($line -match 'role:\s*(.+)' -and $currentDevice) {
            $currentDevice.Role = $Matches[1].Trim()
        }
    }
    if ($currentDevice) { $devices += $currentDevice }

    if ($devices.Count -eq 0) {
        Write-Step "No devices found in structured output; falling back to index scan..."
        # Try indexes 0..7
        for ($i = 0; $i -lt 8; $i++) {
            $devices += @{ Index = $i; Label = "Device $i"; Id = ""; Role = "" }
        }
    }

    Write-Step "Found $($devices.Count) input device(s). Recording $Seconds second(s) from each..."
    New-Item -ItemType Directory -Force -Path $baseDir | Out-Null

    $results = @()
    foreach ($dev in $devices) {
        $idx = $dev.Index
        $label = $dev.Label
        $devDir = Join-Path $baseDir "dev-$idx"
        $logFile = Join-Path $devDir "agent.log"
        New-Item -ItemType Directory -Force -Path $devDir | Out-Null

        Write-Step "Recording device [$idx] $label..."

        $procArgs = @(
            "--capture-mode", "microphone",
            "--duration-sec", $Seconds,
            "--input-device-index", $idx,
            "--save-chunks", $devDir,
            "--dry-run"
        )

        $exitCode = 0
        try {
            & $exe @procArgs 2>&1 | Tee-Object -FilePath $logFile
            $exitCode = $LASTEXITCODE
        } catch {
            $exitCode = 1
        }

        $wavFiles = @(Get-ChildItem -Path $devDir -Filter "*.wav" -File -ErrorAction SilentlyContinue | Sort-Object Name)
        $firstWav = $wavFiles | Select-Object -First 1

        $logText = if (Test-Path $logFile) { Get-Content -Path $logFile -Raw } else { "" }
        $rmsVals = [regex]::Matches($logText, "mic_rms=([0-9.]+)") | ForEach-Object { [double]$_.Groups[1].Value }
        $peakVals = [regex]::Matches($logText, "mic_peak=([0-9.]+)") | ForEach-Object { [double]$_.Groups[1].Value }
        $maxRms = if ($rmsVals.Count -gt 0) { ($rmsVals | Measure-Object -Maximum).Maximum } else { 0.0 }
        $maxPeak = if ($peakVals.Count -gt 0) { ($peakVals | Measure-Object -Maximum).Maximum } else { 0.0 }

        $verdict = "FAILED"
        if ($exitCode -eq 0 -and $wavFiles.Count -gt 0) {
            if ($maxRms -gt 0.01 -and $maxPeak -gt 0.05) {
                $verdict = "GOOD"
            } elseif ($maxRms -gt 0.001) {
                $verdict = "LOW_SIGNAL"
            } else {
                $verdict = "SILENT"
            }
        }

        $wavPath = if ($firstWav) { $firstWav.FullName } else { "(none)" }
        $results += [PSCustomObject]@{
            Index      = $idx
            DeviceName = $label
            RMS        = [math]::Round($maxRms, 6)
            Peak       = [math]::Round($maxPeak, 6)
            WAV        = $wavPath
            Verdict    = $verdict
        }
    }

    Write-Host ""
    Write-Host "=== Microphone Diagnosis Results ===" -ForegroundColor Cyan
    Write-Host ""
    $results | Format-Table -AutoSize

    Write-Host ""
    $goodDevices = $results | Where-Object { $_.Verdict -eq "GOOD" }
    $lowDevices  = $results | Where-Object { $_.Verdict -eq "LOW_SIGNAL" }

    if ($goodDevices) {
        Write-Host "Recommended device(s):" -ForegroundColor Green
        foreach ($d in $goodDevices) {
            Write-Pass "  --input-device-index $($d.Index)  [$($d.DeviceName)]  RMS=$($d.RMS)"
        }
    } elseif ($lowDevices) {
        Write-Host "Low signal device(s) (try increasing Windows input volume):" -ForegroundColor Yellow
        foreach ($d in $lowDevices) {
            Write-Warn "  --input-device-index $($d.Index)  [$($d.DeviceName)]  RMS=$($d.RMS)"
        }
        Write-Host "No GOOD device found. Check microphone permissions and volume in Windows Settings."
    } else {
        Write-Fail "No working microphone found. All devices are silent or failed."
        Write-Host "Check: Windows microphone permissions, physical microphone, input volume."
    }

    Write-Host ""
    Write-Host "Output folder: $baseDir"
    Start-Process $baseDir

} finally {
    Pop-Location
}
