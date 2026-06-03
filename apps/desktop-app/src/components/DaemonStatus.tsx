import { isTauriEnv } from "../tauriCommands";

/** Parse the last mic_rms value from agent log lines. */
export function parseLastRms(logLines: string[]): string {
  for (let i = logLines.length - 1; i >= 0; i--) {
    const m = /mic_rms=([\d.]+)/.exec(logLines[i]);
    if (m) return parseFloat(m[1]).toFixed(4);
  }
  return "";
}

/** Parse the last mic_peak value from agent log lines. */
export function parseLastPeak(logLines: string[]): string {
  for (let i = logLines.length - 1; i >= 0; i--) {
    const m = /mic_peak=([\d.]+)/.exec(logLines[i]);
    if (m) return parseFloat(m[1]).toFixed(4);
  }
  return "";
}

/** Parse the last upload status from agent log lines. */
export function parseLastUploadStatus(logLines: string[]): string {
  for (let i = logLines.length - 1; i >= 0; i--) {
    const line = logLines[i];
    if (line.includes("desktop transcript upload ok")) return "ok";
    if (line.includes("desktop transcript upload failed")) return "failed";
    if (line.includes("dry-run enabled")) return "dry-run (no upload)";
  }
  return "none";
}

/** Derive a human-readable agent state from logs + process state. */
export function deriveAgentState(
  running: boolean,
  logLines: string[],
  lastError?: string | null
): { label: string; color: string } {
  if (!running) {
    if (lastError) return { label: "Error", color: "#dc2626" };
    return { label: "Stopped", color: "#6b7280" };
  }
  const recent = logLines.slice(-10).join("\n");
  if (recent.includes("microphone capture started")) return { label: "Listening", color: "#16a34a" };
  if (recent.includes("mock capture started")) return { label: "Listening (mock)", color: "#16a34a" };
  if (recent.includes("desktop transcript upload ok")) return { label: "Uploading → OK", color: "#2563eb" };
  if (recent.includes("desktop transcript upload failed")) return { label: "Upload failed", color: "#dc2626" };
  if (recent.includes("WARNING microphone seems silent")) return { label: "Silent mic ⚠", color: "#d97706" };
  if (recent.includes("Grey Cardinal desktop agent starting")) return { label: "Starting…", color: "#7c3aed" };
  return { label: "Running", color: "#16a34a" };
}

export function DaemonStatus({
  status,
  configPath,
  logsPath,
  agentCommand,
  running,
  pid,
  lastUploadStatus,
  asrProvider,
  logLines,
  agentError,
  onOpenLogs,
  onOpenConfig,
  onRestartAgent,
}: {
  status: string;
  configPath: string;
  logsPath: string;
  agentCommand: string;
  running: boolean;
  pid: number | null;
  lastUploadStatus: string;
  asrProvider: string;
  logLines: string[];
  agentError: string | null;
  onOpenLogs: () => void;
  onOpenConfig: () => void;
  onRestartAgent: () => void;
}) {
  const inTauri = isTauriEnv();
  const agentState = deriveAgentState(running, logLines, agentError);

  function copyToClipboard() {
    void navigator.clipboard?.writeText(agentCommand);
  }

  const logText = logLines.length > 0 ? logLines.join("\n") : "[no log lines yet]";

  return (
    <section className="panel">
      <h2>Agent</h2>

      <div
        style={{
          background: agentState.color,
          color: "white",
          padding: "3px 10px",
          borderRadius: "12px",
          display: "inline-block",
          fontWeight: 600,
          fontSize: "0.85em",
          marginBottom: "8px",
        }}
      >
        {agentState.label}
      </div>

      <div className="kv">
        <span>process</span>
        <strong>
          {inTauri
            ? running
              ? "running (pid " + (pid ?? "?") + ")"
              : "not running"
            : running
            ? "script launch requested (browser mode)"
            : "not running / unknown"}
        </strong>
      </div>
      <div className="kv">
        <span>ASR</span>
        <strong style={{ color: asrProvider === "mock" ? "#b45309" : "#166534" }}>
          {asrProvider === "mock" ? "⚠ mock (simulated phrases)" : asrProvider}
        </strong>
      </div>
      <div className="kv">
        <span>last upload</span>
        <strong>{lastUploadStatus}</strong>
      </div>
      {agentError && (
        <div style={{ color: "#dc2626", fontSize: "0.83em", marginTop: "4px" }}>
          {agentError}
        </div>
      )}

      <div className="muted" style={{ fontSize: "0.82em", marginTop: "6px" }}>
        app status: {status}
      </div>
      <div className="muted" style={{ fontSize: "0.82em" }}>config: {configPath}</div>
      <div className="muted" style={{ fontSize: "0.82em" }}>logs: {logsPath}</div>

      {inTauri && (
        <div style={{ display: "flex", gap: "6px", marginTop: "8px", flexWrap: "wrap" }}>
          <button onClick={onOpenLogs} style={{ fontSize: "0.82em" }}>Open Logs</button>
          <button onClick={onOpenConfig} style={{ fontSize: "0.82em" }}>Open Config</button>
          {running && (
            <button onClick={onRestartAgent} style={{ fontSize: "0.82em" }}>
              Restart Agent
            </button>
          )}
        </div>
      )}

      {inTauri && (
        <>
          <div style={{ fontWeight: 600, fontSize: "0.82em", marginTop: "10px", marginBottom: "3px" }}>
            Agent log (last {logLines.length} lines):
          </div>
          <textarea
            readOnly
            value={logText}
            rows={12}
            style={{
              fontFamily: "monospace",
              fontSize: "0.72em",
              width: "100%",
              background: "#111827",
              color: "#d1fae5",
              border: "1px solid #374151",
              borderRadius: "3px",
              padding: "4px",
              resize: "vertical",
            }}
          />
        </>
      )}

      {!inTauri && (
        <>
          <div style={{ marginTop: "8px", fontSize: "0.85em", fontWeight: 600 }}>
            Browser mode — script bridge (fallback/dev diagnostics):
          </div>
          <div className="muted" style={{ fontSize: "0.82em", marginBottom: "4px" }}>
            Copy and run in PowerShell (use Tauri app for full desktop experience):
          </div>
          <textarea
            readOnly
            value={agentCommand}
            rows={5}
            style={{ fontFamily: "monospace", fontSize: "0.76em", width: "100%" }}
          />
          <button onClick={copyToClipboard} style={{ marginTop: "4px", fontSize: "0.82em" }}>
            Copy command to clipboard
          </button>
        </>
      )}
    </section>
  );
}
