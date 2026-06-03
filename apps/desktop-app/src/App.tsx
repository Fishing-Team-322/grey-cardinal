import { useEffect, useMemo, useState } from "react";

import {
  BrainClient,
  type DesktopIdentity,
  type DesktopProposal,
  type DesktopTask,
  type DesktopTranscriptItem,
  type GamificationState,
  type MeetingParticipant
} from "./api/brainClient";
import { AppShell } from "./components/AppShell";
import { DaemonStatus } from "./components/DaemonStatus";
import { GamificationPanel } from "./components/GamificationPanel";
import { MeetingPanel } from "./components/MeetingPanel";
import { MicrophonePanel } from "./components/MicrophonePanel";
import { TaskList } from "./components/TaskList";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { defaultBrainUrl, defaultInternalToken, defaultMeetingId, mockPhrases } from "./data/mock";

const storageKey = "grey-cardinal-desktop-v1";
const agentConfigPath = "%LOCALAPPDATA%\\GreyCardinal\\Agent\\config.toml";
const agentLogsPath = "%LOCALAPPDATA%\\GreyCardinal\\Agent\\logs";

// ASR_PROVIDER reflects what the native agent is configured to use.
// Currently always "mock" until real ASR is configured in agent config.
const ASR_PROVIDER = "mock";

type StoredState = {
  brainUrl?: string;
  token?: string;
  displayName?: string;
  telegramUsername?: string;
  meetingId?: string;
  inputDeviceIndex?: number;
  inputDeviceName?: string;
  micGain?: number;
  identity?: DesktopIdentity | null;
};

function loadStoredState(): StoredState {
  try {
    return JSON.parse(localStorage.getItem(storageKey) ?? "{}") as StoredState;
  } catch {
    return {};
  }
}

export function App() {
  const stored = useMemo(loadStoredState, []);
  const [brainUrl, setBrainUrl] = useState(stored.brainUrl ?? defaultBrainUrl);
  const [token, setToken] = useState(stored.token ?? defaultInternalToken);
  const [displayName, setDisplayName] = useState(stored.displayName ?? "Петя");
  const [telegramUsername, setTelegramUsername] = useState(stored.telegramUsername ?? "petya");
  const [meetingId, setMeetingId] = useState(stored.meetingId ?? defaultMeetingId);
  const [inputDeviceIndex, setInputDeviceIndex] = useState(stored.inputDeviceIndex ?? -1);
  const [inputDeviceName, setInputDeviceName] = useState(stored.inputDeviceName ?? "");
  const [micGain, setMicGain] = useState(stored.micGain ?? 1.0);
  const [identity, setIdentity] = useState<DesktopIdentity | null>(stored.identity ?? null);
  const [joined, setJoined] = useState(false);
  const [running, setRunning] = useState(false);
  const [captureMode, setCaptureMode] = useState<"microphone" | "mock">("microphone");
  const [participant, setParticipant] = useState<MeetingParticipant | null>(null);
  const [phrase, setPhrase] = useState(mockPhrases[0]);
  const [lines, setLines] = useState<string[]>([]);
  const [tasks, setTasks] = useState<DesktopTask[]>([]);
  const [proposals, setProposals] = useState<DesktopProposal[]>([]);
  const [recentTranscripts, setRecentTranscripts] = useState<DesktopTranscriptItem[]>([]);
  const [xp, setXp] = useState<GamificationState | null>(null);
  const [status, setStatus] = useState("idle");
  const [lastUploadStatus, setLastUploadStatus] = useState("none");
  const [lastMicRms] = useState("read from agent.log");

  const client = useMemo(
    () => new BrainClient(brainUrl.replace(/\/$/, ""), token),
    [brainUrl, token]
  );

  useEffect(() => {
    localStorage.setItem(
      storageKey,
      JSON.stringify({
        brainUrl, token, displayName, telegramUsername, meetingId,
        inputDeviceIndex, inputDeviceName, micGain, identity
      })
    );
  }, [brainUrl, token, displayName, telegramUsername, meetingId, inputDeviceIndex, inputDeviceName, micGain, identity]);

  useEffect(() => {
    if (!identity) return;
    void refresh(identity);
  }, [identity]);

  useEffect(() => {
    if (!identity) return;
    const tick = async () => {
      try {
        await client.heartbeat(identity, joined ? meetingId : undefined);
      } catch (error) {
        setStatus(`heartbeat error: ${String(error)}`);
      }
    };
    void tick();
    const timer = window.setInterval(tick, 15000);
    return () => window.clearInterval(timer);
  }, [client, identity, joined, meetingId]);

  async function register() {
    try {
      setStatus("registering device...");
      const registered = await client.registerDevice({
        display_name: displayName,
        telegram_username: telegramUsername || undefined,
        device_name: `${displayName} Desktop`,
        platform: "windows",
        app_version: "0.1.0"
      });
      setIdentity(registered);
      setStatus("registered");
    } catch (error) {
      setStatus(`register error: ${String(error)}`);
    }
  }

  async function startSession() {
    if (!identity) return;
    try {
      setStatus("starting session...");
      const session = await client.startSession(identity);
      setIdentity({ ...identity, client_session_id: session.client_session_id });
      setStatus("session active");
    } catch (error) {
      setStatus(`session error: ${String(error)}`);
    }
  }

  async function join() {
    if (!identity) return;
    try {
      setStatus("joining meeting...");
      const joinedParticipant = await client.joinMeeting(identity, meetingId);
      setParticipant(joinedParticipant);
      setJoined(true);
      setStatus("joined");
      await refresh(identity);
    } catch (error) {
      setStatus(`join error: ${String(error)}`);
    }
  }

  async function leave() {
    if (!identity) return;
    try {
      setStatus("leaving meeting...");
      const leftParticipant = await client.leaveMeeting(identity, meetingId);
      setParticipant(leftParticipant);
      setJoined(false);
      setRunning(false);
      setStatus("left");
      await refresh(identity);
    } catch (error) {
      setStatus(`leave error: ${String(error)}`);
    }
  }

  async function sendPhrase() {
    if (!identity || !joined) return;
    try {
      setStatus("sending transcript...");
      await client.sendMockTranscript(identity, meetingId, phrase);
      setLines((current) => [`${displayName}: ${phrase}`, ...current].slice(0, 8));
      setLastUploadStatus("manual desktop transcript ok");
      setStatus("transcript sent");
      await refresh(identity);
    } catch (error) {
      setLastUploadStatus(`manual send error: ${String(error)}`);
      setStatus(`transcript error: ${String(error)}`);
    }
  }

  async function confirmProposal(proposalId: string) {
    if (!identity) return;
    try {
      setStatus("confirming proposal...");
      const result = await client.confirmProposal(identity, proposalId);
      setStatus(`confirmed: ${result.task_public_id ?? "ok"}`);
      setLastUploadStatus(`task created: ${result.task_public_id ?? "ok"}`);
      await refresh(identity);
    } catch (error) {
      setStatus(`confirm error: ${String(error)}`);
    }
  }

  async function rejectProposal(proposalId: string) {
    if (!identity) return;
    try {
      await client.rejectProposal(identity, proposalId);
      setStatus("proposal rejected");
      await refresh(identity);
    } catch (error) {
      setStatus(`reject error: ${String(error)}`);
    }
  }

  async function refresh(currentIdentity = identity) {
    if (!currentIdentity) return;
    const [taskRes, xpRes, proposalRes, transcriptRes] = await Promise.allSettled([
      client.listTasks(currentIdentity),
      client.gamification(currentIdentity),
      client.listProposals(currentIdentity),
      client.recentTranscripts(currentIdentity, 10)
    ]);
    if (taskRes.status === "fulfilled") setTasks(taskRes.value.tasks);
    if (xpRes.status === "fulfilled") setXp(xpRes.value);
    if (proposalRes.status === "fulfilled") setProposals(proposalRes.value.items);
    if (transcriptRes.status === "fulfilled") setRecentTranscripts(transcriptRes.value.items);
  }

  function toggleAgentIntent() {
    setRunning((prev) => !prev);
    if (!running) {
      setStatus("agent start command ready — copy from Daemon panel and run in PowerShell");
    } else {
      setStatus("agent stop requested in UI");
    }
  }

  // Build the exact PowerShell command to run the agent
  const deviceParts: string[] = [];
  if (inputDeviceIndex >= 0) deviceParts.push(`-InputDeviceIndex ${inputDeviceIndex}`);
  if (inputDeviceName) deviceParts.push(`-InputDeviceName "${inputDeviceName}"`);
  if (micGain !== 1.0) deviceParts.push(`-MicGain ${micGain}`);

  const agentCommand =
    identity == null
      ? "# Register device and start session first"
      : [
          `scripts\\windows\\start_desktop_agent_for_identity.ps1`,
          `-BrainUrl "${brainUrl.replace(/\/$/, "")}"`,
          `-Token "${token}"`,
          `-UserId "${identity.user_id}"`,
          `-DeviceId "${identity.device_id}"`,
          `-ClientSessionId "${identity.client_session_id}"`,
          `-WorkspaceId "${identity.workspace_id ?? ""}"`,
          `-DisplayName "${identity.display_name}"`,
          `-MeetingId "${meetingId}"`,
          `-CaptureMode ${captureMode}`,
          ...deviceParts
        ].join(" `\n  ");

  return (
    <AppShell>
      <section className="panel identity-panel">
        <h2>Dev Identity</h2>
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
        <button onClick={register}>Register device</button>
        <button onClick={startSession} disabled={!identity}>Start session</button>
        <div className="muted">{identity ? `user ${identity.user_id}` : "No session"}</div>
      </section>

      <div className="grid">
        <MeetingPanel
          meetingId={meetingId}
          onMeetingId={setMeetingId}
          onJoin={join}
          onLeave={leave}
          joined={joined}
          participant={participant}
        />
        <MicrophonePanel
          running={running}
          captureMode={captureMode}
          onCaptureMode={setCaptureMode}
          inputDeviceIndex={inputDeviceIndex}
          onInputDeviceIndex={setInputDeviceIndex}
          inputDeviceName={inputDeviceName}
          onInputDeviceName={setInputDeviceName}
          micGain={micGain}
          onMicGain={setMicGain}
          lastMicRms={lastMicRms}
          asrProvider={ASR_PROVIDER}
          phrase={phrase}
          onPhrase={setPhrase}
          onToggle={toggleAgentIntent}
          onSend={sendPhrase}
        />
        <DaemonStatus
          status={status}
          configPath={agentConfigPath}
          logsPath={agentLogsPath}
          agentCommand={agentCommand}
          running={running}
          lastUploadStatus={lastUploadStatus}
          asrProvider={ASR_PROVIDER}
        />
        <GamificationPanel state={xp} />
      </div>

      <div className="grid wide">
        <TranscriptPanel
          lines={lines}
          asrProvider={ASR_PROVIDER}
          recentTranscripts={recentTranscripts}
        />
        <TaskList
          tasks={tasks}
          proposals={proposals}
          onConfirm={confirmProposal}
          onReject={rejectProposal}
        />
      </div>
    </AppShell>
  );
}
