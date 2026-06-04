$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$logsDir = Join-Path $env:LOCALAPPDATA "GreyCardinal\Agent\logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
Write-Host "[gc-agent] Opening $logsDir"
Start-Process $logsDir
