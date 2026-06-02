import { useEffect, useRef, useState } from "react";
import { connectEvents, type WebsocketEvent } from "../api/websocket";

const WS_URL =
  (import.meta.env.VITE_BRAIN_WS_URL as string | undefined) ??
  "ws://localhost:8000/ws/events";

type LogLine = { ts: string; event: WebsocketEvent };

export function DashboardPlaceholder() {
  const [connected, setConnected] = useState(false);
  const [log, setLog] = useState<LogLine[]>([]);
  const disconnectRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    disconnectRef.current = connectEvents(WS_URL, (event) => {
      if (event.event === "connected") setConnected(true);
      setLog((prev) => [
        { ts: new Date().toLocaleTimeString(), event },
        ...prev.slice(0, 99),
      ]);
    });
    return () => disconnectRef.current?.();
  }, []);

  return (
    <main style={styles.main}>
      <header style={styles.header}>
        <h1 style={styles.title}>🧠 Grey Cardinal Dashboard</h1>
        <span style={{ ...styles.badge, background: connected ? "#1f9d55" : "#b91c1c" }}>
          {connected ? "WS connected" : "WS connecting…"}
        </span>
      </header>

      <p style={styles.subtitle}>
        P0 placeholder. Здесь будет «live theater»: транскрипт встречи и карточки
        задач в реальном времени. Пока — лог входящих websocket-событий.
      </p>
      <p style={styles.meta}>Источник: {WS_URL}</p>

      <section style={styles.logBox}>
        {log.length === 0 ? (
          <div style={styles.empty}>Событий пока нет. Создайте задачу в Telegram.</div>
        ) : (
          log.map((line, i) => (
            <div key={i} style={styles.logLine}>
              <span style={styles.logTs}>{line.ts}</span>
              <span style={styles.logEvent}>{line.event.event}</span>
              <code style={styles.logPayload}>{JSON.stringify(line.event.payload)}</code>
            </div>
          ))
        )}
      </section>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  main: {
    fontFamily: "system-ui, sans-serif",
    maxWidth: 920,
    margin: "0 auto",
    padding: "32px 20px",
    color: "#e5e7eb",
    background: "#0b1020",
    minHeight: "100vh",
  },
  header: { display: "flex", alignItems: "center", gap: 12 },
  title: { fontSize: 28, margin: 0 },
  badge: { padding: "4px 10px", borderRadius: 999, fontSize: 12, color: "white" },
  subtitle: { color: "#9ca3af", lineHeight: 1.5 },
  meta: { color: "#6b7280", fontSize: 13 },
  logBox: {
    marginTop: 16,
    border: "1px solid #1f2937",
    borderRadius: 12,
    padding: 12,
    background: "#0f172a",
  },
  empty: { color: "#6b7280", padding: 16, textAlign: "center" },
  logLine: {
    display: "flex",
    gap: 12,
    padding: "6px 4px",
    borderBottom: "1px solid #111827",
    fontSize: 13,
  },
  logTs: { color: "#6b7280", minWidth: 86 },
  logEvent: { color: "#38bdf8", minWidth: 160 },
  logPayload: { color: "#a3e635", overflow: "hidden", textOverflow: "ellipsis" },
};
