param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$agentRoot = Join-Path $repoRoot "native\desktop-agent"

Write-Host "[agent] configuring $Configuration build"
cmake -S $agentRoot -B (Join-Path $agentRoot "build") -DCMAKE_BUILD_TYPE=$Configuration
if ($LASTEXITCODE -ne 0) {
    throw "cmake configure failed"
}

Write-Host "[agent] building $Configuration"
cmake --build (Join-Path $agentRoot "build") --config $Configuration
if ($LASTEXITCODE -ne 0) {
    throw "cmake build failed"
}

Write-Host "[agent] build PASS"
