import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  BrainClient,
  type DesktopIdentity,
  type DesktopProposal,
  type DesktopTask,
  type DesktopTranscriptItem,
  type GamificationState,
  type MeetingParticipant,
} from "./api/brainClient";
import { AppShell } from "./components/AppShell";
import {
  DaemonStatus,
  parseLastPeak,
  parseLastRms,
  parseLastUploadStatus,
} from "./components/DaemonStatus";
import { GamificationPanel } from "./components/GamificationPanel";
import { MeetingPanel } from "./components/MeetingPanel";
import { MicrophonePanel } from "./components/MicrophonePanel";
import { TaskList } from "./components/TaskList";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { defaultBrainUrl, defaultInternalToken, defaultMeetingId, mockPhrases } from "./data/mock";
import {
  type InputDevice,
  agentStatus,
  getDefaultConfigPath,
  getDefaultLogPath,
  isTauriEnv,
  listInputDevices,
  openConfigFile,
  openLogsFolder,
  readAgentLogsTail,
  recordMicTest,
  startAgent,
  stopAgent,
} from "./tauriCommands";

const STORAGE_KEY = "grey-cardinal-desktop-v2";
const BROWSER_CONFIG_PATH = "%LOCALAPPDATA%\\GreyCardinal\\Agent\\config.toml";
const BROWSER_LOGS_PATH = "%LOCALAPPDATA%\\GreyCardinal\\Agent\\logs";

// ─── Persisted state ─────────────────────────────────────────────────────────

type StoredState = {
  brainUrl?: string;
  token?: string;
  displayName?: string;
  telegramUsername?: string;
  meetingId?: string;
  inputDeviceIndex?: number;
  inputDeviceId?: string;
  inputDeviceName?: string;
  micGain?: number;
  asrProvider?: string;
  asrUrl?: string;
  identity?: DesktopIdentity | null;
};

function loadStored(): StoredState {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as StoredState;
  } catch {
    return {};
  }
}

// ─── App ─────────────────────────────────────────────────────────────────────

export function App() {
  const stored = useMemo(loadStored, []);
  const inTauri = useMemo(() => isTauriEnv(), []);

  // Connection / identity
  const [brainUrl, setBrainUrl] = useState(stored.brainUrl ?? defaultBrainUrl);
  const [token, setToken] = useState(stored.token ?? defaultInternalToken);
  const [displayName, setDisplayName] = useState(stored.displayName ?? "Петя");
  const [telegramUsername, setTelegramUsername] = useState(stored.telegramUsername ?? "petya");
  const [meetingId, setMeetingId] = useState(stored.meetingId ?? defaultMeetingId);
  const [identity, setIdentity] = useState<DesktopIdentity | null>(stored.identity ?? null);

  // Mic / agent config
  const [inputDeviceIndex, setInputDeviceIndex] = useState(stored.inputDeviceIndex ?? -1);
  const [inputDeviceId, setInputDeviceId] = useState(stored.inputDeviceId ?? "");
  const [inputDeviceName, setInputDeviceName] = useState(stored.inputDeviceName ?? "");
  const [micGain, setMicGain] = useState(stored.micGain ?? 1.0);
  const [asrProvider, setAsrProvider] = useState(stored.asrProvider ?? "mock");
  const [asrUrl, setAsrUrl] = useState(stored.asrUrl ?? "http://localhost:8030/transcribe");
  const [captureMode, setCaptureMode] = useState<"microphone" | "mock">("microphone");

  // Device list (Tauri only)
  const [inputDevices, setInputDevices] = useState<InputDevice[]>([]);
  const [devicesLoading, setDevicesLoading] = useState(false);

  // Agent process state (Tauri only)
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentStarting, setAgentStarting] = useState(false);
  const [agentPid, setAgentPid] = useState<number | null>(null);
  const [agentLogLines, setAgentLogLines] = useState<string[]>([]);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [configPath, setConfigPath] = useState(BROWSER_CONFIG_PATH);
  const [logsPath, setLogsPath] = useState(BROWSER_LOGS_PATH);

  // Browser-mode intent flag (no real process)
  const [browserRunningIntent, setBrowserRunningIntent] = useState(false);

  // Meeting / session
  const [joined, setJoined] = useState(false);
  const [participant, setParticipant] = useState<MeetingParticipant | null>(null);

  // UI data
  const [phrase, setPhrase] = useState(mockPhrases[0]);
  const [lines, setLines] = useState<string[]>([]);
  const [tasks, setTasks] = useState<DesktopTask[]>([]);
  const [proposals, setProposals] = useState<DesktopProposal[]>([]);
  const [recentTranscripts, setRecentTranscripts] = useState<DesktopTranscriptItem[]>([]);
  const [xp, setXp] = useState<GamificationState | null>(null);
  const [status, setStatus] = useState("idle");
  const [lastUploadStatus, setLastUploadStatus] = useState("none");

  // Derived metrics from log lines
  const lastMicRms = parseLastRms(agentLogLines);
  const lastMicPeak = parseLastPeak(agentLogLines);
  const logUpload = parseLastUploadStatus(agentLogLines);
  const effectiveUpload = logUpload !== "none" ? logUpload : lastUploadStatus;

  const client = useMemo(
    () => new BrainClient(brainUrl.replace(/\/$/, ""), token),
    [brainUrl, token]
  );

  // ─── Persist settings ─────────────────────────────────────────────────────

  useEffect(() => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        brainUrl, token, displayName, telegramUsername, meetingId,
        inputDeviceIndex, inputDeviceId, inputDeviceName, micGain,
        asrProvider, asrUrl, identity,
      })
    );
  }, [brainUrl, token, displayName, telegramUsername, meetingId,
      inputDeviceIndex, inputDeviceId, inputDeviceName, micGain,
      asrProvider, asrUrl, identity]);

  // ─── On mount: resolve Tauri paths + load devices ─────────────────────────

  useEffect(() => {
    if (!inTauri) return;
    void (async () => {
      const [cfg, log] = await Promise.all([
        getDefaultConfigPath().catch(() => BROWSER_CONFIG_PATH),
        getDefaultLogPath().catch(() => BROWSER_LOGS_PATH),
      ]);
      setConfigPath(cfg);
      setLogsPath(log);
      await doRefreshDevices();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inTauri]);

  // ─── Poll agent status + logs every 2s (Tauri only) ───────────────────────

  const identityRef = useRef(identity);
  identityRef.current = identity;

  useEffect(() => {
    if (!inTauri) return;
    const tick = async () => {
      try {
        const st = await agentStatus();
        setAgentRunning(st.running);
        setAgentPid(st.pid ?? null);
        if (st.last_error) setAgentError(st.last_error);
        else if (!st.running) setAgentError(null);
        if (st.running && identityRef.current) {
          void refresh(identityRef.current);
        }
      } catch { /* transient IPC errors are fine */ }
      try {
        const tail = await readAgentLogsTail(undefined, 80);
        setAgentLogLines(tail);
      } catch { /* ignore */ }
    };
    const timer = window.setInterval(() => { void tick(); }, 2000);
    void tick();
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inTauri]);

  // ─── Heartbeat ────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!identity) return;
    const tick = async () => {
      try {
        await client.heartbeat(identity, joined ? meetingId : undefined);
      } catch (err) {
        setStatus("heartbeat error: " + String(err));
      }
    };
    void tick();
    const t = window.setInterval(tick, 15000);
    return () => window.clearInterval(t);
  }, [client, identity, joined, meetingId]);

  // ─── Initial data load ────────────────────────────────────────────────────

  useEffect(() => {
    if (!identity) return;
    void refresh(identity);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity]);

  // ─── Device refresh ───────────────────────────────────────────────────────

  const doRefreshDevices = useCallback(async () => {
    setDevicesLoading(true);
    try {
      const devices = await listInputDevices();
      setInputDevices(devices);
      setStatus("devices: " + String(devices.length) + " found");
    } catch (err) {
      setStatus("device list error: " + String(err));
    } finally {
      setDevicesLoading(false);
    }
  }, []);

  // ─── Agent lifecycle ──────────────────────────────────────────────────────

  async function doStartAgent() {
    if (!identity) {
      setStatus("register device and start session first");
      return;
    }
    setAgentStarting(true);
    setAgentError(null);
    setStatus("starting agent…");
    try {
      const pid = await startAgent({
        server_url: brainUrl.replace(/\/$/, ""),
        token,
        user_id: identity.user_id,
        device_id: identity.device_id,
        client_session_id: identity.client_session_id,
        workspace_id: identity.workspace_id ?? null,
        display_name: identity.display_name,
        meeting_id: meetingId,
        capture_mode: captureMode,
        input_device_index: inputDeviceIndex >= 0 ? inputDeviceIndex : null,
        input_device_id: inputDeviceId || null,
        input_device_name: inputDeviceName || null,
        mic_gain: micGain !== 1.0 ? micGain : null,
        asr_provider: asrProvider,
        asr_url: asrProvider === "faster_whisper_http" ? asrUrl : null,
        chunk_ms: null,
      });
      setAgentPid(pid);
      setAgentRunning(true);
      setStatus("agent started (pid " + String(pid) + ")");
    } catch (err) {
      const msg = String(err);
      setAgentError(msg);
      setStatus("agent start error: " + msg);
    } finally {
      setAgentStarting(false);
    }
  }

  async function doStopAgent() {
    setStatus("stopping agent…");
    try {
      await stopAgent();
      setAgentRunning(false);
      setAgentPid(null);
      setStatus("agent stopped");
    } catch (err) {
      setStatus("stop error: " + String(err));
    }
  }

  async function handleToggleAgent() {
    if (inTauri) {
      if (agentRunning) {
        await doStopAgent();
      } else {
        await doStartAgent();
      }
    } else {
      setBrowserRunningIntent((prev) => !prev);
      setStatus(
        !browserRunningIntent
          ? "intent: copy command from Agent panel and run in PowerShell"
          : "agent stop requested in UI (browser mode)"
      );
    }
  }

  async function handleRestartAgent() {
    await doStopAgent();
    await doStartAgent();
  }

  async function handleRecordTest() {
    setStatus("running mic test…");
    try {
      const out = await recordMicTest({
        deviceIndex: inputDeviceIndex >= 0 ? inputDeviceIndex : undefined,
        deviceId: inputDeviceId || undefined,
        deviceName: inputDeviceName || undefined,
        durationSec: 10,
      });
      setStatus("mic test done — check logs");
      const tail = await readAgentLogsTail(undefined, 80);
      setAgentLogLines(tail);
      console.info("[mic test]", out);
    } catch (err) {
      setStatus("mic test error: " + String(err));
    }
  }

  // ─── API actions ──────────────────────────────────────────────────────────

  async function register() {
    try {
      setStatus("registering device...");
      const reg = await client.registerDevice({
        display_name: displayName,
        telegram_username: telegramUsername || undefined,
        device_name: displayName + " Desktop",
        platform: "windows",
        app_version: "0.1.0",
      });
      setIdentity(reg);
      setStatus("registered");
    } catch (err) {
      setStatus("register error: " + String(err));
    }
  }

  async function startSession() {
    if (!identity) return;
    try {
      setStatus("starting session...");
      const session = await client.startSession(identity);
      setIdentity({ ...identity, client_session_id: session.client_session_id });
      setStatus("session active");
    } catch (err) {
      setStatus("session error: " + String(err));
    }
  }

  async function join() {
    if (!identity) return;
    try {
      setStatus("joining meeting...");
      const p = await client.joinMeeting(identity, meetingId);
      setParticipant(p);
      setJoined(true);
      setStatus("joined");
      await refresh(identity);
    } catch (err) {
      setStatus("join error: " + String(err));
    }
  }

  async function leave() {
    if (!identity) return;
    try {
      setStatus("leaving meeting...");
      const p = await client.leaveMeeting(identity, meetingId);
      setParticipant(p);
      setJoined(false);
      if (inTauri && agentRunning) await doStopAgent();
      setBrowserRunningIntent(false);
      setStatus("left");
      await refresh(identity);
    } catch (err) {
      setStatus("leave error: " + String(err));
    }
  }

  async function sendPhrase() {
    if (!identity || !joined) return;
    try {
      setStatus("sending transcript...");
      await client.sendMockTranscript(identity, meetingId, phrase);
      setLines((cur) => [displayName + ": " + phrase, ...cur].slice(0, 8));
      setLastUploadStatus("manual desktop transcript ok");
      setStatus("transcript sent");
      await refresh(identity);
    } catch (err) {
      setLastUploadStatus("manual send error: " + String(err));
      setStatus("transcript error: " + String(err));
    }
  }

  async function confirmProposal(proposalId: string) {
    if (!identity) return;
    try {
      setStatus("confirming proposal...");
      const result = await client.confirmProposal(identity, proposalId);
      setStatus("confirmed: " + (result.task_public_id ?? "ok"));
      setLastUploadStatus("task created: " + (result.task_public_id ?? "ok"));
      await refresh(identity);
    } catch (err) {
      setStatus("confirm error: " + String(err));
    }
  }

  async function rejectProposal(proposalId: string) {
    if (!identity) return;
    try {
      await client.rejectProposal(identity, proposalId);
      setStatus("proposal rejected");
      await refresh(identity);
    } catch (err) {
      setStatus("reject error: " + String(err));
    }
  }

  async function refresh(id = identity) {
    if (!id) return;
    const [taskRes, xpRes, propRes, trRes] = await Promise.allSettled([
      client.listTasks(id),
      client.gamification(id),
      client.listProposals(id),
      client.recentTranscripts(id, 10),
    ]);
    if (taskRes.status === "fulfilled") setTasks(taskRes.value.tasks);
    if (xpRes.status === "fulfilled") setXp(xpRes.value);
    if (propRes.status === "fulfilled") setProposals(propRes.value.items);
    if (trRes.status === "fulfilled") setRecentTranscripts(trRes.value.items);
  }

  function resetIdentity() {
    setIdentity(null);
    setJoined(false);
    setParticipant(null);
    if (inTauri && agentRunning) void doStopAgent();
    setBrowserRunningIntent(false);
    setStatus("identity reset");
  }

  // ─── Browser PowerShell command (fallback) ────────────────────────────────

  const deviceParts: string[] = [];
  if (inputDeviceIndex >= 0) deviceParts.push("-InputDeviceIndex " + String(inputDeviceIndex));
  if (inputDeviceName) deviceParts.push("-InputDeviceName \"" + inputDeviceName + "\"");
  if (micGain !== 1.0) deviceParts.push("-MicGain " + String(micGain));

  const agentCommand =
    identity == null
      ? "# Register device and start session first"
      : [
          "scripts\\windows\\start_desktop_agent_for_identity.ps1",
          "-BrainUrl \"" + brainUrl.replace(/\/$/, "") + "\"",
          "-Token \"" + token + "\"",
          "-UserId \"" + identity.user_id + "\"",
          "-DeviceId \"" + identity.device_id + "\"",
          "-ClientSessionId \"" + identity.client_session_id + "\"",
          "-WorkspaceId \"" + (identity.workspace_id ?? "") + "\"",
          "-DisplayName \"" + identity.display_name + "\"",
          "-MeetingId \"" + meetingId + "\"",
          "-CaptureMode " + captureMode,
          ...deviceParts,
        ].join(" `\n  ");

  const effectiveRunning = inTauri ? agentRunning : browserRunningIntent;

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <AppShell>
      <section className="panel identity-panel">
        <h2>
          Dev Identity{" "}
          {inTauri && (
            <span style={{ fontSize: "0.7em", color: "#16a34a", fontWeight: 400 }}>
              ✓ Tauri
            </span>
          )}
        </h2>
        <label>
          Brain URL
          <input value={brainUrl} onChange={(e) => setBrainUrl(e.target.value)} />
        </label>
        <label>
          Internal token
          <input value={token} onChange={(e) => setToken(e.target.value)} />
        </label>
        <label>
          Display name
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </label>
        <label>
          Telegram username
          <input value={telegramUsername} onChange={(e) => setTelegramUsername(e.target.value)} />
        </label>
        <label>
          ASR provider
          <select
            value={asrProvider}
            onChange={(e) => setAsrProvider(e.target.value)}
            disabled={effectiveRunning}
          >
            <option value="mock">mock (simulated phrases) ⚠</option>
            <option value="faster_whisper_http">faster_whisper_http (real, local service)</option>
            <option value="whisper_cli">whisper_cli (real, CLI)</option>
          </select>
        </label>
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          <button onClick={() => { void register(); }}>Register device</button>
          <button onClick={() => { void startSession(); }} disabled={!identity}>
            Start session
          </button>
          <button
            onClick={resetIdentity}
            style={{ fontSize: "0.82em", opacity: 0.7 }}
          >
            Reset local identity
          </button>
        </div>
        <div className="muted" style={{ marginTop: "4px" }}>
          {identity
            ? "user " + identity.user_id + " · device " + identity.device_id
            : "No identity — click Register device"}
        </div>
      </section>

      <div className="grid">
        <MeetingPanel
          meetingId={meetingId}
          onMeetingId={setMeetingId}
          onJoin={() => { void join(); }}
          onLeave={() => { void leave(); }}
          joined={joined}
          participant={participant}
        />
        <MicrophonePanel
          running={effectiveRunning}
          starting={agentStarting}
          captureMode={captureMode}
          onCaptureMode={setCaptureMode}
          inputDeviceIndex={inputDeviceIndex}
          onInputDeviceIndex={setInputDeviceIndex}
          inputDeviceId={inputDeviceId}
          onInputDeviceId={setInputDeviceId}
          inputDeviceName={inputDeviceName}
          onInputDeviceName={setInputDeviceName}
          micGain={micGain}
          onMicGain={setMicGain}
          lastMicRms={lastMicRms}
          lastMicPeak={lastMicPeak}
          asrProvider={asrProvider}
          asrUrl={asrUrl}
          onAsrUrl={setAsrUrl}
          phrase={phrase}
          onPhrase={setPhrase}
          onToggle={() => { void handleToggleAgent(); }}
          onSend={() => { void sendPhrase(); }}
          onRefreshDevices={() => { void doRefreshDevices(); }}
          onRecordTest={() => { void handleRecordTest(); }}
          inputDevices={inputDevices}
          devicesLoading={devicesLoading}
        />
        <DaemonStatus
          status={status}
          configPath={configPath}
          logsPath={logsPath}
          agentCommand={agentCommand}
          running={effectiveRunning}
          pid={agentPid}
          lastUploadStatus={effectiveUpload}
          asrProvider={asrProvider}
          logLines={agentLogLines}
          agentError={agentError}
          onOpenLogs={() => { void openLogsFolder(); }}
          onOpenConfig={() => { void openConfigFile(); }}
          onRestartAgent={() => { void handleRestartAgent(); }}
        />
        <GamificationPanel state={xp} />
      </div>

      <div className="grid wide">
        <TranscriptPanel
          lines={lines}
          asrProvider={asrProvider}
          recentTranscripts={recentTranscripts}
        />
        <TaskList
          tasks={tasks}
          proposals={proposals}
          onConfirm={(id) => { void confirmProposal(id); }}
          onReject={(id) => { void rejectProposal(id); }}
        />
      </div>
    </AppShell>
  );
}
