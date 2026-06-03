import type { DesktopTranscriptItem } from "../api/brainClient";

export function TranscriptPanel({
  lines,
  asrProvider,
  recentTranscripts
}: {
  lines: string[];
  asrProvider: string;
  recentTranscripts: DesktopTranscriptItem[];
}) {
  const isMock = asrProvider === "mock";

  return (
    <section className="panel transcript">
      <h2>Transcript</h2>
      <div className="kv">
        <span>ASR provider</span>
        <strong style={{ color: isMock ? "var(--warn, #b8860b)" : "var(--ok, #2e7d32)" }}>
          {isMock ? "mock — simulated phrases, NOT real speech" : asrProvider}
        </strong>
      </div>
      {recentTranscripts.length > 0 && (
        <>
          <div className="muted" style={{ fontSize: "0.82em", marginTop: "8px" }}>
            Recent from server ({recentTranscripts.length}):
          </div>
          <div style={{ maxHeight: "150px", overflowY: "auto", fontSize: "0.85em" }}>
            {recentTranscripts.map((t) => (
              <div key={t.id} style={{ padding: "2px 0", borderBottom: "1px solid var(--border)" }}>
                <span className="muted" style={{ fontSize: "0.8em" }}>[{t.asr_provider ?? "?"}]</span>{" "}
                {t.text}
              </div>
            ))}
          </div>
        </>
      )}
      {lines.length > 0 && (
        <>
          <div className="muted" style={{ fontSize: "0.82em", marginTop: "8px" }}>
            Local sent ({lines.length}):
          </div>
          <div style={{ maxHeight: "120px", overflowY: "auto" }}>
            {lines.map((line, index) => (
              <p key={`${line}-${index}`} style={{ margin: "2px 0" }}>{line}</p>
            ))}
          </div>
        </>
      )}
      {lines.length === 0 && recentTranscripts.length === 0 && (
        <div className="muted">No transcript events yet.</div>
      )}
    </section>
  );
}
