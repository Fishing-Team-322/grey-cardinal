/**
 * Typed wrappers around Tauri `invoke()` commands exposed by src-tauri/src/lib.rs.
 *
 * All functions check `isTauriEnv()` first. When running in a plain browser
 * (npm run dev without Tauri), they return safe stubs so the browser dev build
 * still compiles and partially works.
 */

// Tauri v2 exposes `window.__TAURI_INTERNALS__` when running inside the WebView.
export function isTauriEnv(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

// Lazy-import invoke to avoid hard dependency when running in browser
async function invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  const { invoke: tauriInvoke } = await import("@tauri-apps/api/core");
  return tauriInvoke<T>(cmd, args);
}

// ─── Types (mirrored from lib.rs) ────────────────────────────────────────────

export interface InputDevice {
  index: number;
  name: string;
  id: string;
  is_default: boolean;
  role: string | null;
}

export interface AgentStatus {
  running: boolean;
  pid: number | null;
  started_at: number | null; // unix epoch secs
  last_error: string | null;
}

export interface StartAgentArgs {
  server_url: string;
  token: string;
  user_id: string;
  device_id: string;
  client_session_id: string;
  workspace_id?: string | null;
  display_name: string;
  meeting_id: string;
  capture_mode: string;
  input_device_index?: number | null;
  input_device_id?: string | null;
  input_device_name?: string | null;
  mic_gain?: number | null;
  asr_provider?: string | null;
  asr_url?: string | null;
  chunk_ms?: number | null;
}

// ─── Commands ────────────────────────────────────────────────────────────────

/**
 * List available audio input devices from the C++ agent.
 * Throws an error string if the agent binary is not found.
 */
export async function listInputDevices(): Promise<InputDevice[]> {
  if (!isTauriEnv()) {
    console.warn("[tauri stub] list_input_devices: not in Tauri, returning empty list");
    return [];
  }
  return invoke<InputDevice[]>("list_input_devices");
}

/**
 * Write an agent config file to disk.
 * Returns the resolved path that was written.
 */
export async function writeAgentConfig(
  configContent: string,
  configPath?: string
): Promise<string> {
  if (!isTauriEnv()) {
    console.warn("[tauri stub] write_agent_config: not in Tauri");
    return configPath ?? "(browser stub)";
  }
  return invoke<string>("write_agent_config", {
    configPath: configPath ?? null,
    configContent,
  });
}

/**
 * Start the C++ agent sidecar. Returns the PID of the spawned process.
 */
export async function startAgent(args: StartAgentArgs): Promise<number> {
  if (!isTauriEnv()) {
    console.warn("[tauri stub] start_agent: not in Tauri");
    return 0;
  }
  return invoke<number>("start_agent", { args });
}

/**
 * Stop the running agent process.
 */
export async function stopAgent(): Promise<void> {
  if (!isTauriEnv()) {
    console.warn("[tauri stub] stop_agent: not in Tauri");
    return;
  }
  return invoke<void>("stop_agent");
}

/**
 * Check whether the agent process is currently running.
 */
export async function agentStatus(): Promise<AgentStatus> {
  if (!isTauriEnv()) {
    return { running: false, pid: null, started_at: null, last_error: null };
  }
  return invoke<AgentStatus>("agent_status");
}

/**
 * Return the last N lines of the agent log file.
 */
export async function readAgentLogsTail(
  logPath?: string,
  lines = 80
): Promise<string[]> {
  if (!isTauriEnv()) {
    return ["[browser mode: agent logs not available]"];
  }
  return invoke<string[]>("read_agent_logs_tail", {
    logPath: logPath ?? null,
    lines,
  });
}

/**
 * Return the resolved default log file path from the OS.
 */
export async function getDefaultLogPath(): Promise<string> {
  if (!isTauriEnv()) return "%LOCALAPPDATA%\\GreyCardinal\\Agent\\logs\\agent.log";
  return invoke<string>("get_default_log_path");
}

/**
 * Return the resolved default config file path from the OS.
 */
export async function getDefaultConfigPath(): Promise<string> {
  if (!isTauriEnv()) return "%LOCALAPPDATA%\\GreyCardinal\\Agent\\config.toml";
  return invoke<string>("get_default_config_path");
}

/**
 * Open the logs folder in the OS file manager.
 */
export async function openLogsFolder(logsPath?: string): Promise<void> {
  if (!isTauriEnv()) return;
  return invoke<void>("open_logs_folder", { logsPath: logsPath ?? null });
}

/**
 * Open the config file in the system text editor.
 */
export async function openConfigFile(configPath?: string): Promise<void> {
  if (!isTauriEnv()) return;
  return invoke<void>("open_config_file", { configPath: configPath ?? null });
}

/**
 * Record a short mic test (dry-run, no upload).
 * Returns the agent stdout output which includes mic_rms/mic_peak lines.
 */
export async function recordMicTest(opts: {
  deviceIndex?: number;
  deviceId?: string;
  deviceName?: string;
  durationSec?: number;
  savePath?: string;
}): Promise<string> {
  if (!isTauriEnv()) {
    return "[browser mode: mic test not available]";
  }
  return invoke<string>("record_mic_test", {
    deviceIndex: opts.deviceIndex ?? null,
    deviceId: opts.deviceId ?? null,
    deviceName: opts.deviceName ?? null,
    durationSec: opts.durationSec ?? 10,
    savePath: opts.savePath ?? null,
  });
}
