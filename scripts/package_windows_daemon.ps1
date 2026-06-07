param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$buildScript = Join-Path $repoRoot "scripts\windows\build_agent.ps1"
$agentRoot = Join-Path $repoRoot "native\desktop-agent"
$templateDir = Join-Path $agentRoot "package\windows"
$downloadDir = Join-Path $repoRoot "apps\frontend\public\downloads"
$stageDir = Join-Path $repoRoot "apps\frontend\public\downloads\grey-cardinal-daemon-windows"
$zipPath = Join-Path $downloadDir "grey-cardinal-daemon-windows.zip"

& $buildScript -Configuration $Configuration

$exeCandidates = @(
    (Join-Path $agentRoot "build\$Configuration\grey-cardinal-agent.exe"),
    (Join-Path $agentRoot "build\grey-cardinal-agent.exe")
)
$exe = $exeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $exe) {
    throw "grey-cardinal-agent.exe was not found after build"
}

Remove-Item -LiteralPath $stageDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null
New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null

Copy-Item -LiteralPath $exe -Destination (Join-Path $stageDir "grey-cardinal-agent.exe")
Copy-Item -Path (Join-Path $templateDir "*") -Destination $stageDir -Recurse

Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force
Remove-Item -LiteralPath $stageDir -Recurse -Force

$size = (Get-Item -LiteralPath $zipPath).Length
Write-Host "[package] $zipPath"
Write-Host "[package] size_bytes=$size"
