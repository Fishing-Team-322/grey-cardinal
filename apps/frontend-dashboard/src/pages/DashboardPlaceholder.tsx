import { useEffect, useRef, useState } from "react";
import { connectEvents, type WebsocketEvent } from "../api/websocket";
import {
  getMeetings,
  getMeeting,
  getHealth,
  joinTelemost,
  leaveTelemost,
  getTelemostStatus,
  type MeetingSummary,
  type MeetingDetail,
  type BotSessionStatus,
} from "../api";

const WS_URL =
  (import.meta.env.VITE_BRAIN_WS_URL as string | undefined) ??
  "ws://localhost:8000/ws/events";

// ---------------------------------------------------------------------------
// Status badge helper
// ---------------------------------------------------------------------------
const STATUS_COLORS: Record<string, string> = {
  uploaded: "#1d4ed8",
  processing: "#b45309",
  processed: "#1f9d55",
  error: "#b91c1c",
  recording: "#7c3aed",
  created: "#374151",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      style={{
        background: STATUS_COLORS[status] ?? "#374151",
        color: "white",
        borderRadius: 999,
        padding: "2px 8px",
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.03em",
      }}
    >
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Meeting row
// ---------------------------------------------------------------------------
function MeetingRow({
  meeting,
  onClick,
}: {
  meeting: MeetingSummary;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "10px 12px",
        borderBottom: "1px solid #1f2937",
        cursor: "pointer",
        borderRadius: 6,
      }}
      onMouseEnter={(e) =>
        ((e.currentTarget as HTMLDivElement).style.background = "#1e293b")
      }
      onMouseLeave={(e) =>
        ((e.currentTarget as HTMLDivElement).style.background = "transparent")
      }
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: "#f1f5f9", fontWeight: 500 }}>
          {meeting.meeting_id}
        </div>
        <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
          {new Date(meeting.created_at).toLocaleString()} &nbsp;&middot;&nbsp;
          {meeting.audio_count} audio
        </div>
      </div>
      <StatusBadge status={meeting.status} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Meeting detail panel
// ---------------------------------------------------------------------------
function MeetingPanel({
  meeting,
  onClose,
}: {
  meeting: MeetingDetail;
  onClose: () => void;
}) {
  return (
    <div
      style={{
        background: "#0f172a",
        border: "1px solid #1f2937",
        borderRadius: 10,
        padding: 16,
        marginTop: 12,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        <div>
          <span style={{ color: "#f1f5f9", fontWeight: 600 }}>
            {meeting.meeting_id}
          </span>
          &nbsp;&nbsp;
          <StatusBadge status={meeting.status} />
        </div>
        <button
          onClick={onClose}
          style={{
            background: "transparent",
            border: "none",
            color: "#6b7280",
            cursor: "pointer",
            fontSize: 16,
          }}
        >
          ✕
        </button>
      </div>

      <div style={{ marginBottom: 8 }}>
        <div style={{ color: "#9ca3af", fontSize: 12, marginBottom: 4 }}>
          Audio files
        </div>
        {meeting.audios.length === 0 ? (
          <div style={{ color: "#6b7280", fontSize: 12 }}>None</div>
        ) : (
          meeting.audios.map((a) => (
            <div
              key={a.audio_id}
              style={{
                fontSize: 12,
                color: "#94a3b8",
                padding: "3px 0",
                borderBottom: "1px solid #1e293b",
              }}
            >
              <span style={{ color: "#38bdf8" }}>{a.audio_id}</span>{" "}
              &mdash; {a.filename}&nbsp;
              <StatusBadge status={a.status} />
            </div>
          ))
        )}
      </div>

      <div>
        <div style={{ color: "#9ca3af", fontSize: 12, marginBottom: 4 }}>
          Tasks
        </div>
        {meeting.tasks.length === 0 ? (
          <div style={{ color: "#6b7280", fontSize: 12 }}>
            No tasks yet (processing on backend)
          </div>
        ) : (
          meeting.tasks.map((t) => (
            <div key={t.task_id} style={{ fontSize: 12, color: "#94a3b8" }}>
              {t.title}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Telemost control panel
// ---------------------------------------------------------------------------
interface BotSession {
  bot_session_id: string;
  meeting_id: string;
  status: BotSessionStatus;
}

function TelemostPanel() {
  const [url, setUrl] = useState("");
  const [session, setSession] = useState<BotSession | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const BOT_STATUS_COLORS: Record<string, string> = {
    joining: "#b45309",
    joined: "#1d4ed8",
    recording: "#7c3aed",
    left: "#374151",
    error: "#b91c1c",
    uploaded: "#1f9d55",
  };

  const handleJoin = async () => {
    setError("");
    setLoading(true);
    try {
      const res = await joinTelemost(url);
      setSession({ bot_session_id: res.bot_session_id, meeting_id: res.meeting_id, status: res.status });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleLeave = async () => {
    if (!session) return;
    setLoading(true);
    try {
      const res = await leaveTelemost(session.bot_session_id);
      setSession((s) => s ? { ...s, status: res.status } : s);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshStatus = async () => {
    if (!session) return;
    try {
      const res = await getTelemostStatus(session.bot_session_id);
      setSession((s) => s ? { ...s, status: res.status } : s);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div style={{ border: "1px solid #1f2937", borderRadius: 8, padding: 16 }}>
      {!session ? (
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            type="text"
            placeholder="https://telemost.yandex.ru/j/..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            style={{
              flex: 1,
              minWidth: 260,
              background: "#0f172a",
              border: "1px solid #374151",
              borderRadius: 6,
              padding: "6px 10px",
              color: "#e5e7eb",
              fontSize: 13,
            }}
          />
          <button
            onClick={handleJoin}
            disabled={loading || !url}
            style={{ padding: "6px 14px", borderRadius: 6, background: "#1d4ed8", color: "white", border: "none", cursor: "pointer", fontSize: 13 }}
          >
            {loading ? "…" : "Join with bot"}
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "#9ca3af" }}>Session:</span>
            <code style={{ fontSize: 12, color: "#38bdf8" }}>{session.bot_session_id}</code>
            <span style={{ fontSize: 12, color: "#9ca3af" }}>Meeting:</span>
            <code style={{ fontSize: 12, color: "#94a3b8" }}>{session.meeting_id}</code>
            <span style={{
              padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600, color: "white",
              background: BOT_STATUS_COLORS[session.status] ?? "#374151",
            }}>
              {session.status}
            </span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleRefreshStatus}
              style={{ padding: "4px 10px", borderRadius: 6, background: "#374151", color: "white", border: "none", cursor: "pointer", fontSize: 12 }}
            >
              Refresh status
            </button>
            <button
              onClick={handleLeave}
              disabled={loading || session.status === "left"}
              style={{ padding: "4px 10px", borderRadius: 6, background: "#b91c1c", color: "white", border: "none", cursor: "pointer", fontSize: 12 }}
            >
              {loading ? "…" : "Leave"}
            </button>
            <button
              onClick={() => { setSession(null); setUrl(""); }}
              style={{ padding: "4px 10px", borderRadius: 6, background: "transparent", color: "#6b7280", border: "1px solid #374151", cursor: "pointer", fontSize: 12 }}
            >
              New session
            </button>
          </div>
        </div>
      )}
      {error && <div style={{ color: "#f87171", fontSize: 12, marginTop: 6 }}>{error}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main dashboard
// ---------------------------------------------------------------------------
type LogLine = { ts: string; event: WebsocketEvent };

export function DashboardPlaceholder() {
  const [connected, setConnected] = useState(false);
  const [log, setLog] = useState<LogLine[]>([]);
  const [meetings, setMeetings] = useState<MeetingSummary[]>([]);
  const [selectedMeeting, setSelectedMeeting] = useState<MeetingDetail | null>(
    null
  );
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const disconnectRef = useRef<(() => void) | null>(null);

  // Check health + load meetings on mount, refresh every 10s.
  useEffect(() => {
    const load = () => {
      getHealth()
        .then(() => setBackendOk(true))
        .catch(() => setBackendOk(false));
      getMeetings()
        .then(setMeetings)
        .catch(() => {});
    };
    load();
    const interval = setInterval(load, 10_000);
    return () => clearInterval(interval);
  }, []);

  // WebSocket for live events.
  useEffect(() => {
    disconnectRef.current = connectEvents(WS_URL, (event) => {
      if (event.event === "connected") setConnected(true);
      setLog((prev) => [
        { ts: new Date().toLocaleTimeString(), event },
        ...prev.slice(0, 49),
      ]);
    });
    return () => disconnectRef.current?.();
  }, []);

  const openMeeting = async (mid: string) => {
    try {
      const detail = await getMeeting(mid);
      setSelectedMeeting(detail);
    } catch (e) {
      console.error("Failed to load meeting", e);
    }
  };

  return (
    <main style={styles.main}>
      {/* Header */}
      <header style={styles.header}>
        <h1 style={styles.title}>Grey Cardinal</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <span
            style={{
              ...styles.badge,
              background: backendOk === true ? "#1f9d55" : backendOk === false ? "#b91c1c" : "#374151",
            }}
          >
            {backendOk === true ? "API ok" : backendOk === false ? "API down" : "API …"}
          </span>
          <span
            style={{
              ...styles.badge,
              background: connected ? "#1f9d55" : "#b91c1c",
            }}
          >
            {connected ? "WS live" : "WS …"}
          </span>
        </div>
      </header>

      {/* Telemost bot */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>Telemost bot</h2>
        <TelemostPanel />
      </section>

      {/* Meetings */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>
          Meetings{" "}
          <span style={{ color: "#6b7280", fontWeight: 400, fontSize: 13 }}>
            ({meetings.length})
          </span>
        </h2>
        <div
          style={{ border: "1px solid #1f2937", borderRadius: 8, padding: 4 }}
        >
          {meetings.length === 0 ? (
            <div style={styles.empty}>
              No meetings yet. Start the desktop agent to record.
            </div>
          ) : (
            meetings.map((m) => (
              <MeetingRow
                key={m.meeting_id}
                meeting={m}
                onClick={() => openMeeting(m.meeting_id)}
              />
            ))
          )}
        </div>
        {selectedMeeting && (
          <MeetingPanel
            meeting={selectedMeeting}
            onClose={() => setSelectedMeeting(null)}
          />
        )}
      </section>

      {/* Live events log */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>Live events</h2>
        <div style={styles.logBox}>
          {log.length === 0 ? (
            <div style={styles.empty}>Waiting for WebSocket events…</div>
          ) : (
            log.map((line, i) => (
              <div key={i} style={styles.logLine}>
                <span style={styles.logTs}>{line.ts}</span>
                <span style={styles.logEvent}>{line.event.event}</span>
                <code style={styles.logPayload}>
                  {JSON.stringify(line.event.payload)}
                </code>
              </div>
            ))
          )}
        </div>
      </section>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  main: {
    fontFamily: "system-ui, sans-serif",
    maxWidth: 900,
    margin: "0 auto",
    padding: "28px 20px",
    color: "#e5e7eb",
    background: "#0b1020",
    minHeight: "100vh",
  },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 },
  title: { fontSize: 24, margin: 0, color: "#f1f5f9" },
  badge: { padding: "4px 10px", borderRadius: 999, fontSize: 11, color: "white", fontWeight: 600 },
  section: { marginBottom: 28 },
  sectionTitle: { fontSize: 15, color: "#9ca3af", fontWeight: 600, marginBottom: 8, margin: "0 0 10px" },
  empty: { color: "#6b7280", padding: "16px 12px", fontSize: 13 },
  logBox: {
    border: "1px solid #1f2937",
    borderRadius: 8,
    padding: 8,
    background: "#0f172a",
    maxHeight: 300,
    overflowY: "auto",
  },
  logLine: {
    display: "flex",
    gap: 12,
    padding: "5px 4px",
    borderBottom: "1px solid #111827",
    fontSize: 12,
  },
  logTs: { color: "#6b7280", minWidth: 70 },
  logEvent: { color: "#38bdf8", minWidth: 150 },
  logPayload: { color: "#a3e635", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
};
