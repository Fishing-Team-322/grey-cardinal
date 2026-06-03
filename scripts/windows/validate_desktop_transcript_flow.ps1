param(
    [string]$BrainUrl = "http://localhost:8010",
    [string]$Token = "dev-internal-token",
    [string]$DisplayName = "Петя",
    [string]$TelegramUsername = "petya",
    [string]$MeetingId = "MTG-1",
    [int]$Seconds = 10,
    [switch]$StartDocker,
    [switch]$DownAfter
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$startAgentScript = Join-Path $PSScriptRoot "start_desktop_agent_for_identity.ps1"
$runDir = Join-Path "C:\Temp\GreyCardinal\desktop-flow" (Get-Date -Format "yyyyMMdd-HHmmss")
$agentLog = Join-Path $runDir "agent-flow.log"

function Write-Step([string]$Message) {
    Write-Host "[check] $Message"
}

function Write-Pass([string]$Message) {
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Write-Fail([string]$Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Headers($Identity = $null) {
    $headers = @{ "X-Internal-Token" = $Token }
    if ($Identity) {
        $headers["X-GC-User-Id"] = $Identity.user_id
        $headers["X-GC-Device-Id"] = $Identity.device_id
        $headers["X-GC-Client-Session-Id"] = $Identity.client_session_id
    }
    return $headers
}

function Invoke-JsonPost([string]$Uri, $Body, $Identity = $null) {
    Invoke-RestMethod `
        -Method Post `
        -Uri $Uri `
        -Headers (Headers $Identity) `
        -ContentType "application/json; charset=utf-8" `
        -Body ($Body | ConvertTo-Json -Depth 10)
}

function Wait-Health([string]$Url) {
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            $response = Invoke-RestMethod -Method Get -Uri "$Url/health" -TimeoutSec 3
            if ($response) {
                return
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "brain-api health did not become ready at $Url/health"
}

Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null

    Write-Step "verifying branch"
    $branch = (git branch --show-current).Trim()
    if ($branch -ne "demonSSS") {
        throw "expected branch demonSSS, got $branch"
    }
    Write-Pass "branch is demonSSS"

    if ($StartDocker) {
        Write-Step "starting docker compose full profile"
        docker compose --profile full up --build -d
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose up failed"
        }
        Write-Pass "compose stack started"
    }

    Write-Step "checking brain-api health"
    Wait-Health $BrainUrl
    Write-Pass "brain-api health is ready"

    Write-Step "registering desktop device"
    $identity = Invoke-JsonPost "$BrainUrl/desktop/devices/register" @{
        display_name = $DisplayName
        telegram_username = $TelegramUsername
        device_name = "$DisplayName Desktop"
        platform = "windows"
        app_version = "0.1.0"
    }
    Write-Pass "registered user=$($identity.user_id) device=$($identity.device_id) session=$($identity.client_session_id)"

    Write-Step "joining meeting $MeetingId"
    $participant = Invoke-JsonPost "$BrainUrl/desktop/meetings/$MeetingId/join" @{
        display_name = $DisplayName
        metadata = @{ validation = "desktop_transcript_flow" }
    } $identity
    Write-Pass "participant status=$($participant.status)"

    Write-Step "starting native agent microphone + mock ASR for $Seconds second(s)"
    $workspaceId = if ($identity.workspace_id) { $identity.workspace_id } else { "" }
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $startAgentScript `
            -BrainUrl $BrainUrl `
            -Token $Token `
            -UserId $identity.user_id `
            -DeviceId $identity.device_id `
            -ClientSessionId $identity.client_session_id `
            -WorkspaceId $workspaceId `
            -DisplayName $DisplayName `
            -MeetingId $MeetingId `
            -CaptureMode microphone `
            -DurationSec $Seconds `
            -SaveChunks $runDir 2>&1 | Tee-Object -FilePath $agentLog
        $agentExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($agentExitCode -ne 0) {
        throw "agent exited with code $agentExitCode"
    }

    $wavFiles = @(Get-ChildItem -Path $runDir -Filter "*.wav" -File -ErrorAction SilentlyContinue | Sort-Object Name)
    if ($wavFiles.Count -eq 0) {
        throw "agent did not create microphone WAV chunks in $runDir"
    }
    Write-Pass "agent created $($wavFiles.Count) WAV chunk(s); first=$($wavFiles[0].FullName)"

    Write-Step "checking recent desktop transcripts"
    $recent = Invoke-RestMethod -Method Get -Uri "$BrainUrl/internal/audio/transcripts/recent?limit=50" -Headers (Headers)
    $matches = @($recent.items) | Where-Object {
        $_.meeting_public_id -eq $MeetingId -and
        $_.speaker_id -eq $identity.user_id -and
        $_.source -eq "desktop_app"
    }
    if ($matches.Count -eq 0) {
        throw "no accepted desktop_app transcript found for meeting=$MeetingId user=$($identity.user_id)"
    }
    Write-Pass "found $($matches.Count) accepted desktop transcript event(s)"

    Write-Step "checking desktop tasks endpoint"
    $tasks = Invoke-RestMethod -Method Get -Uri "$BrainUrl/desktop/tasks" -Headers (Headers $identity)
    Write-Pass "desktop tasks endpoint returned $(@($tasks.tasks).Count) task(s)"

    Write-Step "checking gamification endpoint"
    $xp = Invoke-RestMethod -Method Get -Uri "$BrainUrl/desktop/gamification/me" -Headers (Headers $identity)
    if ($xp.user_id -ne $identity.user_id) {
        throw "gamification user mismatch"
    }
    Write-Pass "gamification returned level=$($xp.level) points=$($xp.points_total)"

    Write-Host ""
    Write-Pass "desktop transcript flow validation complete"
    Write-Host "[summary] run_dir=$runDir"
    Write-Host "[summary] agent_log=$agentLog"
    Write-Host "[summary] first_wav=$($wavFiles[0].FullName)"
} catch {
    Write-Fail $_.Exception.Message
    Write-Host "[summary] run_dir=$runDir"
    Write-Host "[summary] agent_log=$agentLog"
    exit 1
} finally {
    if ($DownAfter) {
        Write-Step "stopping compose stack because -DownAfter was provided"
        docker compose --profile full down
    }
    Pop-Location
}
