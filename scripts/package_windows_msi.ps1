param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [string]$Version = "0.3.0",
    [string]$WixVersion = "6.0.2"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$buildScript = Join-Path $repoRoot "scripts\windows\build_agent.ps1"
$agentRoot = Join-Path $repoRoot "native\desktop-agent"
$templateDir = Join-Path $agentRoot "package\windows"
$wixSource = Join-Path $agentRoot "installer\windows\wix\GreyCardinalDaemon.wxs"
$toolsDir = Join-Path $repoRoot ".tools"
$wixExe = Join-Path $toolsDir "wix.exe"
$downloadDir = Join-Path $repoRoot "apps\frontend-dashboard\public\downloads"
$stageDir = Join-Path $downloadDir "grey-cardinal-daemon-windows-msi-stage"
$msiPath = Join-Path $downloadDir "grey-cardinal-daemon-windows-x64.msi"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw "dotnet SDK is required to install/run WiX CLI"
}

if (-not (Test-Path $wixExe)) {
    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
    dotnet tool install --tool-path $toolsDir wix --version $WixVersion
    if ($LASTEXITCODE -ne 0) {
        throw "failed to install WiX CLI dotnet tool"
    }
}

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

Copy-Item -LiteralPath $exe -Destination (Join-Path $stageDir "grey-cardinal-daemon.exe")

$trayCandidates = @(
    (Join-Path $agentRoot "build\$Configuration\grey-cardinal-tray.exe"),
    (Join-Path $agentRoot "build\grey-cardinal-tray.exe")
)
$tray = $trayCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $tray) {
    throw "grey-cardinal-tray.exe was not found after build"
}
Copy-Item -LiteralPath $tray -Destination (Join-Path $stageDir "grey-cardinal-tray.exe")

Copy-Item -Path (Join-Path $templateDir "*") -Destination $stageDir -Recurse

Remove-Item -LiteralPath $msiPath -Force -ErrorAction SilentlyContinue
& $wixExe build $wixSource `
    -arch x64 `
    -d "StageDir=$stageDir" `
    -d "ProductVersion=$Version" `
    -out $msiPath

if ($LASTEXITCODE -ne 0) {
    throw "WiX MSI build failed"
}

Remove-Item -LiteralPath $stageDir -Recurse -Force

$item = Get-Item -LiteralPath $msiPath
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $msiPath).Hash
Write-Host "[package] $msiPath"
Write-Host "[package] size_bytes=$($item.Length)"
Write-Host "[package] sha256=$hash"
