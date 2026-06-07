param(
    [string]$Version = "0.6.2",
    [string]$WixVersion = "6.0.2"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$agentRoot = Join-Path $repoRoot "native\tray-agent"
$wixSource = Join-Path $agentRoot "installer\windows\GreyCardinalAgent.wxs"
$toolsDir = Join-Path $repoRoot ".tools"
$wixExe = Join-Path $toolsDir "wix.exe"
$downloadDir = Join-Path $repoRoot "apps\frontend\public\downloads"
$stageDir = Join-Path $repoRoot "build\grey-cardinal-agent-msi-stage"
$msiPath = Join-Path $downloadDir "GreyCardinalAgent-x64.msi"
$agentExe = Join-Path $agentRoot "dist\GreyCardinalAgent.exe"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw "dotnet SDK is required to install/run WiX CLI"
}
if (-not (Test-Path -LiteralPath $wixExe)) {
    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
    dotnet tool install --tool-path $toolsDir wix --version $WixVersion
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install WiX CLI $WixVersion"
    }
}

Push-Location $agentRoot
try {
    python -m PyInstaller --clean --noconfirm GreyCardinalAgent.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed"
    }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $agentExe)) {
    throw "GreyCardinalAgent.exe was not found after build"
}

$resolvedRoot = [System.IO.Path]::GetFullPath($repoRoot.Path)
$resolvedStage = [System.IO.Path]::GetFullPath($stageDir)
if (-not $resolvedStage.StartsWith($resolvedRoot + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Unsafe MSI stage path: $resolvedStage"
}

Remove-Item -LiteralPath $resolvedStage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $resolvedStage | Out-Null
New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
Copy-Item -LiteralPath $agentExe -Destination (Join-Path $resolvedStage "GreyCardinalAgent.exe")

Remove-Item -LiteralPath $msiPath -Force -ErrorAction SilentlyContinue
& $wixExe build $wixSource `
    -arch x64 `
    -d "StageDir=$resolvedStage" `
    -d "ProductVersion=$Version" `
    -out $msiPath
if ($LASTEXITCODE -ne 0) {
    throw "WiX MSI build failed"
}

Remove-Item -LiteralPath $resolvedStage -Recurse -Force

$item = Get-Item -LiteralPath $msiPath
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $msiPath).Hash
Write-Host "[package] $msiPath"
Write-Host "[package] size_bytes=$($item.Length)"
Write-Host "[package] sha256=$hash"
