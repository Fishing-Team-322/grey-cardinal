export function DaemonStatus({
  status,
  configPath,
  logsPath,
  agentCommand,
  running,
  lastUploadStatus
}: {
  status: string;
  configPath: string;
  logsPath: string;
  agentCommand: string;
  running: boolean;
  lastUploadStatus: string;
}) {
  return (
    <section className="panel">
      <h2>Daemon</h2>
      <div className="status-pill">{status}</div>
      <div className="kv">
        <span>process</span>
        <strong>{running ? "script requested" : "not running / unknown"}</strong>
      </div>
      <div className="kv">
        <span>last upload</span>
        <strong>{lastUploadStatus}</strong>
      </div>
      <div className="muted">config: {configPath}</div>
      <div className="muted">logs: {logsPath}</div>
      <textarea readOnly value={agentCommand} rows={4} />
    </section>
  );
}
