param(
    [switch]$DownAfter,
    [string]$Token = "dev-internal-token",
    [string]$MeetingId = "demo-meeting",
    [string]$ExpectedText = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$brainUrl = "http://localhost:8010"
$audioUrl = "http://localhost:8020"

function Write-Step([string]$Message) {
    Write-Host "[check] $Message"
}

function Write-Pass([string]$Message) {
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function New-TinyWavBytes {
    $sampleRate = 16000
    $channels = 1
    $bitsPerSample = 16
    $durationSeconds = 1
    $byteRate = $sampleRate * $channels * ($bitsPerSample / 8)
    $blockAlign = $channels * ($bitsPerSample / 8)
    $dataSize = [int]($byteRate * $durationSeconds)

    $memory = New-Object System.IO.MemoryStream
    $writer = New-Object System.IO.BinaryWriter($memory)
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("RIFF"))
    $writer.Write([UInt32](36 + $dataSize))
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("WAVE"))
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("fmt "))
    $writer.Write([UInt32]16)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]$channels)
    $writer.Write([UInt32]$sampleRate)
    $writer.Write([UInt32]$byteRate)
    $writer.Write([UInt16]$blockAlign)
    $writer.Write([UInt16]$bitsPerSample)
    $writer.Write([System.Text.Encoding]::ASCII.GetBytes("data"))
    $writer.Write([UInt32]$dataSize)
    $writer.Write((New-Object byte[] $dataSize))
    $writer.Flush()
    return $memory.ToArray()
}

function Wait-Health([string]$Url, [string]$Name) {
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            $response = Invoke-RestMethod -Method Get -Uri "$Url/health" -TimeoutSec 3
            if ($response) {
                Write-Pass "$Name health is ready"
                return
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "$Name health did not become ready at $Url/health"
}

Push-Location $repoRoot
try {
    Write-Step "verifying branch"
    $branch = (git branch --show-current).Trim()
    if ($branch -ne "demonSSS") {
        throw "expected branch demonSSS, got $branch"
    }
    Write-Pass "branch is demonSSS"

    Write-Step "checking Docker engine"
    docker version --format "{{.Server.Version}}" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker engine is not available; start Docker Desktop"
    }
    Write-Pass "Docker engine is available"

    Write-Step "validating docker compose config"
    docker compose --profile full config | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose config failed"
    }
    Write-Pass "docker compose config is valid"

    Write-Step "starting full compose profile"
    docker compose --profile full up --build -d
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed"
    }
    Write-Pass "compose stack started"

    Wait-Health $brainUrl "brain-api"
    Wait-Health $audioUrl "audio-worker"

    Write-Step "posting generated WAV chunk to audio-worker"
    $headers = @{
        "X-Internal-Token" = $Token
        "X-Meeting-Id" = $MeetingId
        "X-Chunk-Seq" = "1"
        "X-Audio-Format" = "wav"
        "X-Audio-Sample-Rate" = "16000"
        "X-Audio-Channels" = "1"
        "X-Audio-Bits-Per-Sample" = "16"
    }
    $upload = Invoke-RestMethod -Method Post -Uri "$audioUrl/audio/chunk" -Headers $headers -ContentType "audio/wav" -Body (New-TinyWavBytes)
    if (-not $upload.ok) {
        throw "audio-worker upload response was not ok"
    }
    if ([string]::IsNullOrWhiteSpace($ExpectedText)) {
        $ExpectedText = $upload.text
    }
    Write-Pass "audio-worker accepted WAV chunk"

    Write-Step "querying brain-api recent transcripts"
    $recent = Invoke-RestMethod -Method Get -Uri "$brainUrl/internal/audio/transcripts/recent" -Headers @{"X-Internal-Token" = $Token}
    $match = @($recent.items) | Where-Object { $_.meeting_id -eq $MeetingId -and $_.text -eq $ExpectedText }
    if (-not $match) {
        throw "expected transcript was not found in brain-api recent transcripts"
    }
    Write-Pass "brain-api received expected transcript event"

    Write-Pass "audio pipeline validation complete"
} finally {
    if ($DownAfter) {
        Write-Step "stopping compose stack because -DownAfter was provided"
        docker compose --profile full down
    }
    Pop-Location
}
