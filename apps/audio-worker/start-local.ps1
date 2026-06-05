# Запуск audio-worker локально с faster-whisper
# Использование: .\start-local.ps1 [-Model base|small|medium] [-Port 8020]
param(
    [string]$Model = "base",
    [int]$Port = 8020
)

$venv = "$PSScriptRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $venv)) {
    Write-Error "venv not found. Run setup first:
  py -3.12 -m venv .venv
  .venv\Scripts\pip install -e ..\..\packages\contracts\python
  .venv\Scripts\pip install -e .[whisper]"
    exit 1
}

Write-Host "Starting audio-worker on port $Port with Whisper model '$Model'..." -ForegroundColor Cyan
Write-Host "Health: http://localhost:$Port/health" -ForegroundColor Green

$env:INTERNAL_API_TOKEN       = "dev-internal-token"
$env:BRAIN_API_BASE_URL       = "http://localhost:8000"
$env:AUDIO_ASR_PROVIDER       = "faster_whisper"
$env:AUDIO_FASTER_WHISPER_MODEL = $Model
$env:AUDIO_WORKER_SAVE_CHUNKS = "false"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

Set-Location "$PSScriptRoot\src"
& $venv -m uvicorn audio_worker.main:app --host 0.0.0.0 --port $Port --log-level info
