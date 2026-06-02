export function DaemonStatus({ status }: { status: string }) {
  return (
    <section className="panel">
      <h2>Daemon</h2>
      <div className="status-pill">{status}</div>
    </section>
  );
}
