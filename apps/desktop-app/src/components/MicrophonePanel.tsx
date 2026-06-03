import { mockPhrases } from "../data/mock";

export function MicrophonePanel({
  running,
  captureMode,
  onCaptureMode,
  lastMicRms,
  phrase,
  onPhrase,
  onToggle,
  onSend
}: {
  running: boolean;
  captureMode: "microphone" | "mock";
  onCaptureMode: (value: "microphone" | "mock") => void;
  lastMicRms: string;
  phrase: string;
  onPhrase: (value: string) => void;
  onToggle: () => void;
  onSend: () => void;
}) {
  return (
    <section className="panel">
      <h2>Microphone</h2>
      <label>
        Input device
        <select value="default_input" disabled>
          <option value="default_input">default_input</option>
        </select>
      </label>
      <label>
        Capture mode
        <select
          value={captureMode}
          onChange={(event) => onCaptureMode(event.target.value as "microphone" | "mock")}
        >
          <option value="microphone">microphone</option>
          <option value="mock">mock</option>
        </select>
      </label>
      <button onClick={onToggle}>{running ? "Stop listening" : "Start listening"}</button>
      <div className="muted">last mic RMS: {lastMicRms}</div>
      <select value={phrase} onChange={(event) => onPhrase(event.target.value)}>
        {mockPhrases.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
      <button onClick={onSend} disabled={!running}>
        Send UI mock phrase
      </button>
    </section>
  );
}
