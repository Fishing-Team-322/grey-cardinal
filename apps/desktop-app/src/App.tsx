import { useMemo, useState } from "react";

import { BrainClient, type DesktopIdentity, type DesktopTask, type GamificationState } from "./api/brainClient";
import { AppShell } from "./components/AppShell";
import { DaemonStatus } from "./components/DaemonStatus";
import { GamificationPanel } from "./components/GamificationPanel";
import { MeetingPanel } from "./components/MeetingPanel";
import { MicrophonePanel } from "./components/MicrophonePanel";
import { TaskList } from "./components/TaskList";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { defaultBrainUrl, defaultInternalToken, defaultMeetingId, mockPhrases } from "./data/mock";

export function App() {
  const [brainUrl, setBrainUrl] = useState(defaultBrainUrl);
  const [token, setToken] = useState(defaultInternalToken);
  const [displayName, setDisplayName] = useState("Петя");
  const [telegramUsername, setTelegramUsername] = useState("petya");
  const [meetingId, setMeetingId] = useState(defaultMeetingId);
  const [identity, setIdentity] = useState<DesktopIdentity | null>(null);
  const [joined, setJoined] = useState(false);
  const [running, setRunning] = useState(false);
  const [phrase, setPhrase] = useState(mockPhrases[0]);
  const [lines, setLines] = useState<string[]>([]);
  const [tasks, setTasks] = useState<DesktopTask[]>([]);
  const [xp, setXp] = useState<GamificationState | null>(null);
  const [status, setStatus] = useState("idle");

  const client = useMemo(() => new BrainClient(brainUrl.replace(/\/$/, ""), token), [brainUrl, token]);

  async function register() {
    setStatus("registering device");
    const registered = await client.registerDevice({
      display_name: displayName,
      telegram_username: telegramUsername || undefined,
      device_name: `${displayName} Desktop`,
      platform: "windows",
      app_version: "0.1.0"
    });
    setIdentity(registered);
    setStatus("registered");
  }

  async function join() {
    if (!identity) return;
    setStatus("joining meeting");
    await client.joinMeeting(identity, meetingId);
    setJoined(true);
    setStatus("joined");
    await refresh(identity);
  }

  async function sendPhrase() {
    if (!identity || !joined) return;
    setStatus("sending transcript");
    await client.sendMockTranscript(identity, meetingId, phrase);
    setLines((current) => [`${displayName}: ${phrase}`, ...current].slice(0, 8));
    setStatus("transcript sent");
    await refresh(identity);
  }

  async function refresh(currentIdentity = identity) {
    if (!currentIdentity) return;
    const [taskResponse, xpResponse] = await Promise.all([
      client.listTasks(currentIdentity),
      client.gamification(currentIdentity)
    ]);
    setTasks(taskResponse.tasks);
    setXp(xpResponse);
  }

  return (
    <AppShell>
      <section className="panel identity-panel">
        <h2>Dev Identity</h2>
        <label>
          Brain URL
          <input value={brainUrl} onChange={(event) => setBrainUrl(event.target.value)} />
        </label>
        <label>
          Internal token
          <input value={token} onChange={(event) => setToken(event.target.value)} />
        </label>
        <label>
          Display name
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </label>
        <label>
          Telegram username
          <input value={telegramUsername} onChange={(event) => setTelegramUsername(event.target.value)} />
        </label>
        <button onClick={register}>Register device</button>
        <div className="muted">{identity ? `user ${identity.user_id}` : "No session"}</div>
      </section>

      <div className="grid">
        <MeetingPanel meetingId={meetingId} onMeetingId={setMeetingId} onJoin={join} joined={joined} />
        <MicrophonePanel
          running={running}
          phrase={phrase}
          onPhrase={setPhrase}
          onToggle={() => setRunning((value) => !value)}
          onSend={sendPhrase}
        />
        <DaemonStatus status={status} />
        <GamificationPanel state={xp} />
      </div>

      <div className="grid wide">
        <TranscriptPanel lines={lines} />
        <TaskList tasks={tasks} />
      </div>
    </AppShell>
  );
}
