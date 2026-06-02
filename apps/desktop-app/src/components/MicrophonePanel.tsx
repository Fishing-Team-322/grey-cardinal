import { mockPhrases } from "../data/mock";

export function MicrophonePanel({
  running,
  phrase,
  onPhrase,
  onToggle,
  onSend
}: {
  running: boolean;
  phrase: string;
  onPhrase: (value: string) => void;
  onToggle: () => void;
  onSend: () => void;
}) {
  return (
    <section className="panel">
      <h2>Microphone</h2>
      <button onClick={onToggle}>{running ? "Stop mock mic" : "Start mock mic"}</button>
      <select value={phrase} onChange={(event) => onPhrase(event.target.value)}>
        {mockPhrases.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
      <button onClick={onSend} disabled={!running}>
        Send mock phrase
      </button>
    </section>
  );
}
