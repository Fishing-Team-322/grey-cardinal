export function TranscriptPanel({ lines }: { lines: string[] }) {
  return (
    <section className="panel transcript">
      <h2>Transcript Outbox</h2>
      {lines.length === 0 ? (
        <div className="muted">No local transcript events yet.</div>
      ) : (
        lines.map((line, index) => <p key={`${line}-${index}`}>{line}</p>)
      )}
    </section>
  );
}
