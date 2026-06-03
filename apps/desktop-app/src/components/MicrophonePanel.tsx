import { mockPhrases } from "../data/mock";
import type { InputDevice } from "../tauriCommands";
import { isTauriEnv } from "../tauriCommands";

export function MicrophonePanel({
  running,
  starting,
  captureMode,
  onCaptureMode,
  inputDeviceIndex,
  onInputDeviceIndex,
  inputDeviceId,
  onInputDeviceId,
  inputDeviceName,
  onInputDeviceName,
  micGain,
  onMicGain,
  lastMicRms,
  lastMicPeak,
  asrProvider,
  asrUrl,
  onAsrUrl,
  phrase,
  onPhrase,
  onToggle,
  onSend,
  onRefreshDevices,
  onRecordTest,
  inputDevices,
  devicesLoading,
}: {
  running: boolean;
  starting: boolean;
  captureMode: "microphone" | "mock";
  onCaptureMode: (value: "microphone" | "mock") => void;
  inputDeviceIndex: number;
  onInputDeviceIndex: (value: number) => void;
  inputDeviceId: string;
  onInputDeviceId: (value: string) => void;
  inputDeviceName: string;
  onInputDeviceName: (value: string) => void;
  micGain: number;
  onMicGain: (value: number) => void;
  lastMicRms: string;
  lastMicPeak: string;
  asrProvider: string;
  asrUrl: string;
  onAsrUrl: (value: string) => void;
  phrase: string;
  onPhrase: (value: string) => void;
  onToggle: () => void;
  onSend: () => void;
  onRefreshDevices: () => void;
  onRecordTest: () => void;
  inputDevices: InputDevice[];
  devicesLoading: boolean;
}) {
  const rmsNum = parseFloat(lastMicRms);
  const isSilent = !isNaN(rmsNum) && rmsNum > 0 && rmsNum <= 0.001;
  const hasRms = !isNaN(rmsNum) && rmsNum > 0;
  const inTauri = isTauriEnv();

  function handleDeviceSelect(deviceId: string) {
    const device = inputDevices.find((d) => d.id === deviceId);
    if (!device) return;
    onInputDeviceIndex(device.index);
    onInputDeviceId(device.id);
    onInputDeviceName(device.name);
  }

  return (
    <section className="panel">
      <h2>Microphone</h2>

      {inTauri && (
        <div style={{ marginBottom: "8px" }}>
          <div style={{ display: "flex", gap: "6px", alignItems: "center", marginBottom: "4px" }}>
            <select
              value={inputDeviceId}
              onChange={(e) => handleDeviceSelect(e.target.value)}
              style={{ flex: 1 }}
              disabled={running || devicesLoading}
            >
              <option value="">— select device —</option>
              {inputDevices.map((d) => (
                <option key={d.id || String(d.index)} value={d.id}>
                  {d.is_default ? "★ " : ""}[{d.index}] {d.name}
                  {d.role ? " (" + d.role + ")" : ""}
                </option>
              ))}
            </select>
            <button
              onClick={onRefreshDevices}
              disabled={running || devicesLoading}
              title="Refresh device list from agent"
            >
              {devicesLoading ? "…" : "Refresh"}
            </button>
          </div>
          {inputDevices.length === 0 && !devicesLoading && (
            <div className="muted" style={{ fontSize: "0.82em" }}>
              No devices — click Refresh (requires built C++ agent)
            </div>
          )}
        </div>
      )}

      {!inTauri && (
        <>
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
              {inputDeviceIndex < 0 ? "(default comms device)" : "[" + inputDeviceIndex + "]"}
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
        </>
      )}

      <label>
        Capture mode
        <select
          value={captureMode}
          onChange={(e) => onCaptureMode(e.target.value as "microphone" | "mock")}
          disabled={running}
        >
          <option value="microphone">microphone (real audio)</option>
          <option value="mock">mock (simulated audio, no mic needed)</option>
        </select>
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
          disabled={running}
        />
      </label>

      <div className="kv">
        <span>ASR mode</span>
        <strong style={{ color: asrProvider === "mock" ? "#b45309" : "#166534" }}>
          {asrProvider === "mock" ? "⚠ MOCK — simulated phrases, not real speech" : asrProvider}
        </strong>
      </div>
      {asrProvider === "faster_whisper_http" && (
        <label>
          ASR service URL
          <input
            type="text"
            value={asrUrl}
            onChange={(e) => onAsrUrl(e.target.value)}
            placeholder="http://localhost:8030/transcribe"
            disabled={running}
          />
        </label>
      )}
      {asrProvider === "mock" && (
        <div
          style={{
            background: "#fef3c7",
            border: "1px solid #fcd34d",
            padding: "6px 8px",
            borderRadius: "4px",
            fontSize: "0.82em",
            marginBottom: "4px",
          }}
        >
          Mock ASR active — transcripts are pre-configured phrases, not real speech.
          Start <code>apps/asr-service</code> and choose{" "}
          <code>faster_whisper_http</code> for real ASR.
        </div>
      )}

      <div className="kv">
        <span>mic RMS / peak</span>
        <strong style={{ color: isSilent ? "red" : hasRms ? "#166534" : undefined }}>
          {lastMicRms !== "" ? lastMicRms : "—"} / {lastMicPeak !== "" ? lastMicPeak : "—"}
        </strong>
      </div>
      {isSilent && (
        <div style={{ background: "#fff3cd", padding: "6px 8px", borderRadius: "4px", fontSize: "0.85em" }}>
          ⚠ Microphone seems silent. Select a different device or check Windows input volume.
        </div>
      )}

      <div style={{ display: "flex", gap: "6px", marginTop: "10px", flexWrap: "wrap" }}>
        <button
          onClick={onToggle}
          disabled={starting}
          style={{
            background: running ? "#dc2626" : "#16a34a",
            color: "white",
            border: "none",
            padding: "8px 18px",
            borderRadius: "4px",
            cursor: starting ? "wait" : "pointer",
            fontWeight: 600,
            fontSize: "1em",
          }}
        >
          {starting ? "Starting…" : running ? "■ Stop Listening" : "▶ Start Listening"}
        </button>

        {inTauri && !running && (
          <button onClick={onRecordTest} title="10-second dry-run capture (no upload)">
            Record 10-sec test
          </button>
        )}
      </div>

      {!inTauri && (
        <div className="muted" style={{ marginTop: "6px", fontSize: "0.8em" }}>
          Browser mode: Start Listening marks intent only. See Agent panel for the PowerShell command.
        </div>
      )}

      <hr />
      <div className="muted" style={{ fontSize: "0.85em", marginBottom: "4px" }}>
        Send manual mock phrase (tests brain-api directly, no agent needed)
      </div>
      <div style={{ display: "flex", gap: "6px" }}>
        <select value={phrase} onChange={(e) => onPhrase(e.target.value)} style={{ flex: 1 }}>
          {mockPhrases.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <button onClick={onSend}>Send</button>
      </div>
    </section>
  );
}
