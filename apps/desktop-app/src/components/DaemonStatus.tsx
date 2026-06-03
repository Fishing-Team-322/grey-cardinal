export function DaemonStatus({
  status,
  configPath,
  logsPath,
  agentCommand,
  running,
  lastUploadStatus,
  asrProvider
}: {
  status: string;
  configPath: string;
  logsPath: string;
  agentCommand: string;
  running: boolean;
  lastUploadStatus: string;
  asrProvider: string;
}) {
  function copyToClipboard() {
    void navigator.clipboard?.writeText(agentCommand);
  }

  return (
    <section className="panel">
      <h2>Daemon</h2>
      <div className="status-pill">{status}</div>
      <div className="kv">
        <span>agent process</span>
        <strong>{running ? "script launch requested" : "not running / unknown"}</strong>
      </div>
      <div className="kv">
        <span>ASR</span>
        <strong>{asrProvider === "mock" ? "mock (simulated phrases)" : asrProvider}</strong>
      </div>
      <div className="kv">
        <span>last upload</span>
        <strong>{lastUploadStatus}</strong>
      </div>
      <div className="muted" style={{ fontSize: "0.82em" }}>config: {configPath}</div>
      <div className="muted" style={{ fontSize: "0.82em" }}>logs: {logsPath}</div>
      <div style={{ marginTop: "8px", fontSize: "0.85em", fontWeight: 600 }}>
        Native bridge: script-based in this dev build.
      </div>
      <div className="muted" style={{ fontSize: "0.82em", marginBottom: "4px" }}>
        Copy and run in PowerShell:
      </div>
      <textarea readOnly value={agentCommand} rows={5} style={{ fontFamily: "monospace", fontSize: "0.76em", width: "100%" }} />
      <button onClick={copyToClipboard} style={{ marginTop: "4px", fontSize: "0.82em" }}>
        Copy command to clipboard
      </button>
    </section>
  );
}
