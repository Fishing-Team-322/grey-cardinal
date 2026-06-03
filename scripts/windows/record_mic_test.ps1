param(
    [int]$Seconds = 10,
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

    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    Write-Host "[mic-test] Speak into the local microphone for $Seconds second(s)." -ForegroundColor Yellow
    Write-Host "[mic-test] WAV chunks will be saved to $runDir"

    & $exe `
        --capture-mode microphone `
        --duration-sec $Seconds `
        --save-chunks $runDir `
        --dry-run 2>&1 | Tee-Object -FilePath $logPath

    $files = @(Get-ChildItem -Path $runDir -Filter "*.wav" -File -ErrorAction SilentlyContinue | Sort-Object Name)
    $first = $files | Select-Object -First 1
    $logText = Get-Content -Path $logPath -Raw
    $rmsValues = [regex]::Matches($logText, "mic_rms=([0-9.]+)") | ForEach-Object {
        [double]$_.Groups[1].Value
    }
    $maxRms = if (@($rmsValues).Count -gt 0) { ($rmsValues | Measure-Object -Maximum).Maximum } else { 0 }

    if ($first) {
        Write-Host "[mic-test] first WAV: $($first.FullName)"
    }
    Start-Process $runDir

    $pass = $false
    if ($files.Count -gt 0 -and $first.Length -gt 0 -and $logText.Contains("mic_rms=") -and $maxRms -gt 0) {
        $pass = $true
    }

    if ($pass) {
        Write-Host "[PASS] microphone WAV chunks were created and mic_rms was non-zero (max=$maxRms)" -ForegroundColor Green
        if ($maxRms -le 0.0005) {
            Write-Warning "mic_rms is non-zero but very low; speak louder or check input level before judging audibility."
        }
    } else {
        $firstSize = if ($first) { $first.Length } else { 0 }
        Write-Host "[FAIL] microphone test did not meet all checks" -ForegroundColor Red
        Write-Host "       wav_count=$($files.Count) first_size=$firstSize max_rms=$maxRms log=$logPath"
        exit 1
    }
} finally {
    Pop-Location
}
