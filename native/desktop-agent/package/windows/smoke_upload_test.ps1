param(
    [string]$BackendUrl = "https://fishingteam.su",
    [string]$AgentId = "agent-demo-001",
    [string]$MeetingId = "daemon-smoke-windows",
    [string]$WavPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-TestWav([string]$Path) {
    $sampleRate = 8000
    $durationSeconds = 1
    $samples = $sampleRate * $durationSeconds
    $dataSize = $samples * 2
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
    $writer = [System.IO.BinaryWriter]::new($stream)
    try {
        $writer.Write([System.Text.Encoding]::ASCII.GetBytes("RIFF"))
        $writer.Write([int](36 + $dataSize))
        $writer.Write([System.Text.Encoding]::ASCII.GetBytes("WAVEfmt "))
        $writer.Write([int]16)
        $writer.Write([int16]1)
        $writer.Write([int16]1)
        $writer.Write([int]$sampleRate)
        $writer.Write([int]($sampleRate * 2))
        $writer.Write([int16]2)
        $writer.Write([int16]16)
        $writer.Write([System.Text.Encoding]::ASCII.GetBytes("data"))
        $writer.Write([int]$dataSize)
        for ($i = 0; $i -lt $samples; $i++) {
            $value = [int16](12000 * [Math]::Sin(2 * [Math]::PI * 440 * $i / $sampleRate))
            $writer.Write($value)
        }
    } finally {
        $writer.Dispose()
        $stream.Dispose()
    }
}

if (-not $WavPath) {
    $outDir = Join-Path $env:TEMP "grey-cardinal-smoke"
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $WavPath = Join-Path $outDir "daemon-smoke.wav"
    Write-TestWav $WavPath
}

$uploadUrl = ($BackendUrl.TrimEnd("/")) + "/api/audio/upload"
$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
Write-Host "[gc-agent] Uploading $WavPath to $uploadUrl"

$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if (-not $curl) {
    throw "curl.exe was not found. Install curl or use PowerShell 7+ Invoke-RestMethod multipart manually."
}

$raw = & $curl.Source `
    -sS `
    -X POST $uploadUrl `
    -F "audio=@$WavPath;type=audio/wav" `
    -F "agent_id=$AgentId" `
    -F "meeting_id=$MeetingId" `
    -F "source=desktop_agent" `
    -F "started_at=$now" `
    -F "ended_at=$now"

if ($LASTEXITCODE -ne 0) {
    throw "curl.exe upload failed with exit code $LASTEXITCODE"
}

$response = $raw | ConvertFrom-Json
$response | ConvertTo-Json -Depth 8
if (-not $response.ok) {
    throw "Backend did not return ok=true"
}

Write-Host "[PASS] Upload accepted. Open $($BackendUrl.TrimEnd('/'))/app and refresh; the Daemon uploads panel should list meeting $MeetingId."
