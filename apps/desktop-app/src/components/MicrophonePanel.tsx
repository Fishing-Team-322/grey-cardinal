import { mockPhrases } from "../data/mock";

export function MicrophonePanel({
  running,
  captureMode,
  onCaptureMode,
  inputDeviceIndex,
  onInputDeviceIndex,
  inputDeviceName,
  onInputDeviceName,
  micGain,
  onMicGain,
  lastMicRms,
  asrProvider,
  phrase,
  onPhrase,
  onToggle,
  onSend
}: {
  running: boolean;
  captureMode: "microphone" | "mock";
  onCaptureMode: (value: "microphone" | "mock") => void;
  inputDeviceIndex: number;
  onInputDeviceIndex: (value: number) => void;
  inputDeviceName: string;
  onInputDeviceName: (value: string) => void;
  micGain: number;
  onMicGain: (value: number) => void;
  lastMicRms: string;
  asrProvider: string;
  phrase: string;
  onPhrase: (value: string) => void;
  onToggle: () => void;
  onSend: () => void;
}) {
  const rmsNum = parseFloat(lastMicRms);
  const isSilent = !isNaN(rmsNum) && rmsNum <= 0.001;

  return (
    <section className="panel">
      <h2>Microphone</h2>
      <label>
        Capture mode
        <select
          value={captureMode}
          onChange={(e) => onCaptureMode(e.target.value as "microphone" | "mock")}
        >
          <option value="microphone">microphone</option>
          <option value="mock">mock (simulated audio)</option>
        </select>
      </label>
      <label>
        Device index
        <input
          type="number"
          min={-1}
          value={inputDeviceIndex}
          onChange={(e) => onInputDeviceIndex(parseInt(e.target.value, 10) || -1)}
          placeholder="-1 = default"
          style={{ width: "80px" }}
        />
        <span className="muted" style={{ marginLeft: "6px", fontSize: "0.85em" }}>
          {inputDeviceIndex < 0 ? "(default comms device)" : `[${inputDeviceIndex}]`}
        </span>
      </label>
      <label>
        Device name filter
        <input
          type="text"
          value={inputDeviceName}
          onChange={(e) => onInputDeviceName(e.target.value)}
          placeholder="substring, e.g. Realtek"
        />
      </label>
      <label>
        Mic gain
        <input
          type="number"
          min={0.1}
          max={10}
          step={0.1}
          value={micGain}
          onChange={(e) => onMicGain(parseFloat(e.target.value) || 1.0)}
          style={{ width: "70px" }}
        />
      </label>
      <div className="kv">
        <span>ASR mode</span>
        <strong>{asrProvider === "mock" ? "mock — simulated phrases" : asrProvider}</strong>
      </div>
      {asrProvider === "mock" && (
        <div className="muted" style={{ fontSize: "0.8em" }}>
          ASR: mock — transcripts are simulated, not real speech. Set asr_provider in config for real ASR.
        </div>
      )}
      <div className="kv">
        <span>last mic RMS</span>
        <strong style={{ color: isSilent ? "red" : undefined }}>{lastMicRms}</strong>
      </div>
      {isSilent && (
        <div style={{ background: "#fff3cd", padding: "6px 8px", borderRadius: "4px", fontSize: "0.85em" }}>
          Microphone seems silent. Try a different device index or run diagnose_microphones.ps1
        </div>
      )}
      <button onClick={onToggle} style={{ marginTop: "8px" }}>
        {running ? "Stop Listening" : "Start Listening"}
      </button>
      <div className="muted" style={{ marginTop: "4px", fontSize: "0.8em" }}>
        Native bridge: script-based in this dev build. See Daemon panel for the exact command.
      </div>
      <hr />
      <div className="muted" style={{ fontSize: "0.85em", marginBottom: "4px" }}>Manual mock phrase</div>
      <select value={phrase} onChange={(e) => onPhrase(e.target.value)}>
        {mockPhrases.map((item) => (
          <option key={item} value={item}>{item}</option>
        ))}
      </select>
      <button onClick={onSend}>Send UI mock phrase</button>
    </section>
  );
}
