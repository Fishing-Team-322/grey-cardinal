param(
    [int]$Seconds = 10,
    [int]$DeviceIndex = -1,
    [string]$DeviceId = "",
    [string]$DeviceName = "",
    [float]$MicGain = 1.0,
    [switch]$Interactive,
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$agentRoot = Join-Path $repoRoot "native\desktop-agent"
$buildScript = Join-Path $PSScriptRoot "build_agent.ps1"
$baseDir = "C:\Temp\GreyCardinal\mic-test"
$runDir = Join-Path $baseDir (Get-Date -Format "yyyyMMdd-HHmmss")
$logPath = Join-Path $runDir "record_mic_test.log"
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

    # Interactive device selection
    if ($Interactive -and $DeviceIndex -lt 0 -and -not $DeviceId -and -not $DeviceName) {
        Write-Host ""
        Write-Host "Available input devices:" -ForegroundColor Cyan
        & $exe --list-input-devices
        Write-Host ""
        $inputIdx = Read-Host "Enter device index to use (or press Enter for default)"
        if ($inputIdx -match '^\d+$') {
            $DeviceIndex = [int]$inputIdx
        }
    }

    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    Write-Host "[mic-test] Recording $Seconds second(s) of audio..." -ForegroundColor Yellow
    Write-Host "[mic-test] WAV chunks will be saved to $runDir"

    # Build device selection args
    $deviceArgs = @()
    if ($DeviceId) {
        $deviceArgs += "--input-device-id", $DeviceId
        Write-Host "[mic-test] Using device ID: $DeviceId"
    } elseif ($DeviceIndex -ge 0) {
        $deviceArgs += "--input-device-index", $DeviceIndex
        Write-Host "[mic-test] Using device index: $DeviceIndex"
    } elseif ($DeviceName) {
        $deviceArgs += "--input-device-name", $DeviceName
        Write-Host "[mic-test] Using device name filter: $DeviceName"
    } else {
        Write-Host "[mic-test] Using default communications input device"
    }

    $gainArgs = @()
    if ($MicGain -ne 1.0) {
        $gainArgs += "--mic-gain", $MicGain
    }

    & $exe `
        --capture-mode microphone `
        --duration-sec $Seconds `
        --save-chunks $runDir `
        --dry-run `
        @deviceArgs `
        @gainArgs `
        2>&1 | Tee-Object -FilePath $logPath

    $files = @(Get-ChildItem -Path $runDir -Filter "*.wav" -File -ErrorAction SilentlyContinue | Sort-Object Name)
    $first = $files | Select-Object -First 1
    $logText = if (Test-Path $logPath) { Get-Content -Path $logPath -Raw } else { "" }

    $rmsValues = [regex]::Matches($logText, "mic_rms=([0-9.]+)") | ForEach-Object {
        [double]$_.Groups[1].Value
    }
    $peakValues = [regex]::Matches($logText, "mic_peak=([0-9.]+)") | ForEach-Object {
        [double]$_.Groups[1].Value
    }
    $maxRms = if (@($rmsValues).Count -gt 0) { ($rmsValues | Measure-Object -Maximum).Maximum } else { 0 }
    $maxPeak = if (@($peakValues).Count -gt 0) { ($peakValues | Measure-Object -Maximum).Maximum } else { 0 }

    Write-Host ""
    if ($first) {
        Write-Host "[mic-test] WAV path: $($first.FullName)" -ForegroundColor Cyan
    }
    Write-Host "[mic-test] max mic_rms=$maxRms  max mic_peak=$maxPeak"

    # Open output folder
    if (Test-Path $runDir) {
        Start-Process $runDir
    }

    # PASS only if RMS and peak are above threshold
    $rmsThreshold = 0.001
    $peakThreshold = 0.01

    $pass = $files.Count -gt 0 -and $maxRms -gt $rmsThreshold -and $maxPeak -gt $peakThreshold

    if ($pass) {
        Write-Host "[PASS] Microphone captured real audio (max_rms=$maxRms max_peak=$maxPeak)" -ForegroundColor Green
        Write-Host "       WAV: $($first.FullName)"
    } else {
        Write-Host "[FAIL] Microphone test failed" -ForegroundColor Red
        Write-Host "       wav_count=$($files.Count)  max_rms=$maxRms  max_peak=$maxPeak"
        Write-Host "       Threshold: rms > $rmsThreshold, peak > $peakThreshold"
        if ($maxRms -le $rmsThreshold) {
            Write-Warning "mic_rms is near zero. The WAV may be silent."
            Write-Warning "Try: --DeviceIndex <n> or --DeviceName <substr> or increase Windows input volume."
            Write-Warning "Run diagnose_microphones.ps1 to find which device has good signal."
        }
        exit 1
    }
} finally {
    Pop-Location
}
