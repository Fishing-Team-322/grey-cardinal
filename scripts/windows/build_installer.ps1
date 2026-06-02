param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$agentRoot = Join-Path $repoRoot "native\desktop-agent"
$installerScript = Join-Path $agentRoot "installer\windows\grey-cardinal-agent.iss"
$buildAgent = Join-Path $PSScriptRoot "build_agent.ps1"

function Find-Iscc {
    $command = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 5\ISCC.exe"
    )

    return $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

Push-Location $repoRoot
try {
    $iscc = Find-Iscc
    if (-not $iscc) {
        Write-Error "Inno Setup compiler iscc.exe was not found. Install Inno Setup 6 to build the installer."
        exit 1
    }

    & $buildAgent -Configuration $Configuration

    Write-Host "[installer] building $installerScript"
    & $iscc $installerScript
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup build failed"
    }

    Write-Host "[installer] build PASS"
} finally {
    Pop-Location
}
