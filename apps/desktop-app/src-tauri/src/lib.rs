use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, State};

// ─── Agent process state ────────────────────────────────────────────────────

#[derive(Default)]
struct AgentManager {
    inner: Mutex<AgentInner>,
}

#[derive(Default)]
struct AgentInner {
    child: Option<Child>,
    started_at: Option<u64>, // unix secs
    pid: Option<u32>,
    last_error: Option<String>,
}

// ─── Shared types ────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct InputDevice {
    pub index: i32,
    pub name: String,
    pub id: String,
    pub is_default: bool,
    pub role: Option<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct AgentStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub started_at: Option<u64>,
    pub last_error: Option<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct StartAgentArgs {
    pub server_url: String,
    pub token: String,
    pub user_id: String,
    pub device_id: String,
    pub client_session_id: String,
    pub workspace_id: Option<String>,
    pub display_name: String,
    pub meeting_id: String,
    pub capture_mode: String,
    pub input_device_index: Option<i32>,
    pub input_device_id: Option<String>,
    pub input_device_name: Option<String>,
    pub mic_gain: Option<f32>,
    pub asr_provider: Option<String>,
    pub asr_url: Option<String>,
    pub chunk_ms: Option<i32>,
}

// ─── Agent binary discovery ──────────────────────────────────────────────────

fn find_agent_exe(app: &AppHandle) -> Option<PathBuf> {
    // 1. Explicit env override (useful in dev / CI)
    if let Ok(path) = std::env::var("GREY_CARDINAL_AGENT_EXE") {
        let p = PathBuf::from(path);
        if p.exists() {
            return Some(p);
        }
    }

    // 2. Alongside the running Tauri binary (release bundle)
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(dir) = exe_path.parent() {
            let candidate = dir.join("grey-cardinal-agent.exe");
            if candidate.exists() {
                return Some(candidate);
            }
        }
    }

    // 3. Tauri resource directory (for bundled resources declared in tauri.conf.json)
    if let Ok(resource_dir) = app.path().resource_dir() {
        let candidate = resource_dir.join("grey-cardinal-agent.exe");
        if candidate.exists() {
            return Some(candidate);
        }
    }

    // 4. Dev-mode candidates relative to the Tauri app working directory
    let dev_candidates = [
        "native/desktop-agent/build/Release/grey-cardinal-agent.exe",
        "../native/desktop-agent/build/Release/grey-cardinal-agent.exe",
        "../../native/desktop-agent/build/Release/grey-cardinal-agent.exe",
        // Debug build fallback
        "native/desktop-agent/build/Debug/grey-cardinal-agent.exe",
        "../native/desktop-agent/build/Debug/grey-cardinal-agent.exe",
    ];
    for rel in &dev_candidates {
        let p = PathBuf::from(rel);
        if p.exists() {
            return Some(p);
        }
    }

    None
}

fn agent_not_found_msg() -> String {
    "grey-cardinal-agent.exe not found. \
     Build the C++ agent first:\n  \
     cd native\\desktop-agent && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --config Release\n\
     Or set GREY_CARDINAL_AGENT_EXE env var."
        .to_string()
}

// ─── Default log path ────────────────────────────────────────────────────────

fn default_log_path() -> PathBuf {
    if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
        return PathBuf::from(local_app_data)
            .join("GreyCardinal")
            .join("Agent")
            .join("logs")
            .join("agent.log");
    }
    if let Ok(home) = std::env::var("HOME") {
        return PathBuf::from(home)
            .join(".local")
            .join("state")
            .join("grey-cardinal-agent")
            .join("logs")
            .join("agent.log");
    }
    PathBuf::from("agent.log")
}

fn default_logs_dir() -> PathBuf {
    default_log_path()
        .parent()
        .unwrap_or(&PathBuf::from("."))
        .to_path_buf()
}

fn default_config_path() -> PathBuf {
    if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
        return PathBuf::from(local_app_data)
            .join("GreyCardinal")
            .join("Agent")
            .join("config.toml");
    }
    if let Ok(home) = std::env::var("HOME") {
        return PathBuf::from(home)
            .join(".config")
            .join("grey-cardinal-agent")
            .join("config.toml");
    }
    PathBuf::from("grey-cardinal-agent-config.toml")
}

// ─── Tauri commands ──────────────────────────────────────────────────────────

/// List available audio input devices by running the agent with --list-input-devices.
#[tauri::command]
fn list_input_devices(app: AppHandle) -> Result<Vec<InputDevice>, String> {
    let agent = find_agent_exe(&app).ok_or_else(agent_not_found_msg)?;

    let output = Command::new(&agent)
        .arg("--list-input-devices")
        .output()
        .map_err(|e| format!("Failed to run agent: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);

    if !output.status.success() {
        return Err(format!(
            "Agent exited with error (code {:?}):\n{stderr}",
            output.status.code()
        ));
    }

    // Parse output format produced by main.cpp:
    //   Input devices:
    //   * [0] Communications: Realtek HD Audio Mic
    //       id: {GUID}
    //       role: communications
    //     [1] Microphone (USB)
    //       id: {GUID}
    let mut devices: Vec<InputDevice> = Vec::new();
    let lines: Vec<&str> = stdout.lines().collect();
    let mut i = 0;
    while i < lines.len() {
        let line = lines[i];
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed == "Input devices:" {
            i += 1;
            continue;
        }

        let is_default = trimmed.starts_with("* ");
        let rest = if is_default {
            trimmed.trim_start_matches("* ")
        } else {
            trimmed.trim_start_matches("  ")
        };

        if !rest.starts_with('[') {
            i += 1;
            continue;
        }

        if let Some(bracket_end) = rest.find(']') {
            let index_str = &rest[1..bracket_end];
            let after_bracket = rest[bracket_end + 1..].trim();

            // "Communications: Name" → role="Communications", name="Name"
            // "Name" → role=None, name="Name"
            let (role, name) = if let Some(colon_pos) = after_bracket.find(": ") {
                (
                    Some(after_bracket[..colon_pos].to_string()),
                    after_bracket[colon_pos + 2..].to_string(),
                )
            } else {
                (None, after_bracket.to_string())
            };

            let index = index_str.parse::<i32>().unwrap_or(-1);

            // Collect following id:/role: lines
            let mut device_id = String::new();
            let mut device_role: Option<String> = role;
            while i + 1 < lines.len() {
                let next = lines[i + 1].trim();
                if let Some(id_val) = next.strip_prefix("id: ") {
                    device_id = id_val.to_string();
                    i += 1;
                } else if let Some(role_val) = next.strip_prefix("role: ") {
                    device_role = Some(role_val.to_string());
                    i += 1;
                } else {
                    break;
                }
            }

            devices.push(InputDevice {
                index,
                name,
                id: device_id,
                is_default,
                role: device_role,
            });
        }

        i += 1;
    }

    Ok(devices)
}

/// Write a TOML config file for the agent (creates parent dirs as needed).
#[tauri::command]
fn write_agent_config(config_path: Option<String>, config_content: String) -> Result<String, String> {
    let path = config_path
        .map(PathBuf::from)
        .unwrap_or_else(default_config_path);

    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create config directory: {e}"))?;
    }

    std::fs::write(&path, &config_content)
        .map_err(|e| format!("Failed to write config file: {e}"))?;

    Ok(path.to_string_lossy().to_string())
}

/// Spawn the C++ agent sidecar with the supplied identity and audio config.
/// Returns the PID of the spawned process.
#[tauri::command]
fn start_agent(
    app: AppHandle,
    args: StartAgentArgs,
    state: State<AgentManager>,
) -> Result<u32, String> {
    let agent = find_agent_exe(&app).ok_or_else(agent_not_found_msg)?;

    let mut inner = state.inner.lock().map_err(|e| e.to_string())?;

    // Kill any existing agent before starting a new one
    if let Some(mut child) = inner.child.take() {
        let _ = child.kill();
        let _ = child.wait();
    }

    let mut cmd_args: Vec<String> = vec![
        "--server".to_string(),
        args.server_url.clone(),
        "--token".to_string(),
        args.token.clone(),
        "--user-id".to_string(),
        args.user_id.clone(),
        "--device-id".to_string(),
        args.device_id.clone(),
        "--client-session-id".to_string(),
        args.client_session_id.clone(),
        "--display-name".to_string(),
        args.display_name.clone(),
        "--meeting-id".to_string(),
        args.meeting_id.clone(),
        "--capture-mode".to_string(),
        args.capture_mode.clone(),
    ];

    if let Some(ref ws) = args.workspace_id {
        if !ws.is_empty() {
            cmd_args.extend(["--workspace-id".to_string(), ws.clone()]);
        }
    }

    if let Some(idx) = args.input_device_index {
        if idx >= 0 {
            cmd_args.extend(["--input-device-index".to_string(), idx.to_string()]);
        }
    }

    if let Some(ref id) = args.input_device_id {
        if !id.is_empty() {
            cmd_args.extend(["--input-device-id".to_string(), id.clone()]);
        }
    }

    if let Some(ref name) = args.input_device_name {
        if !name.is_empty() {
            cmd_args.extend(["--input-device-name".to_string(), name.clone()]);
        }
    }

    if let Some(gain) = args.mic_gain {
        if (gain - 1.0_f32).abs() > 0.001 {
            cmd_args.extend(["--mic-gain".to_string(), gain.to_string()]);
        }
    }

    let asr = args.asr_provider.as_deref().unwrap_or("mock");
    cmd_args.extend(["--asr-provider".to_string(), asr.to_string()]);

    if let Some(ref asr_url) = args.asr_url {
        if !asr_url.is_empty() {
            cmd_args.extend(["--asr-url".to_string(), asr_url.clone()]);
        }
    }

    if let Some(ms) = args.chunk_ms {
        cmd_args.extend(["--chunk-ms".to_string(), ms.to_string()]);
    }

    let child = Command::new(&agent)
        .args(&cmd_args)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("Failed to spawn grey-cardinal-agent: {e}"))?;

    let pid = child.id();
    inner.pid = Some(pid);
    inner.child = Some(child);
    inner.started_at = Some(
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs(),
    );
    inner.last_error = None;

    Ok(pid)
}

/// Terminate the running agent process cleanly.
#[tauri::command]
fn stop_agent(state: State<AgentManager>) -> Result<(), String> {
    let mut inner = state.inner.lock().map_err(|e| e.to_string())?;

    if let Some(mut child) = inner.child.take() {
        // On Windows the only cross-platform option without unsafe code is kill().
        // The agent handles SIGTERM/SIGINT in its main loop; kill() will cause it
        // to exit but may skip the graceful flush. That's acceptable for v0.
        let _ = child.kill();
        let _ = child.wait();
    }

    inner.pid = None;
    inner.started_at = None;

    Ok(())
}

/// Return whether the agent process is currently running plus metadata.
#[tauri::command]
fn agent_status(state: State<AgentManager>) -> AgentStatus {
    let mut inner = match state.inner.lock() {
        Ok(g) => g,
        Err(e) => e.into_inner(),
    };

    let running = if let Some(ref mut child) = inner.child {
        match child.try_wait() {
            Ok(None) => true, // still alive
            Ok(Some(status)) => {
                if !status.success() {
                    inner.last_error = Some(format!("agent exited with {status}"));
                }
                inner.child = None;
                inner.pid = None;
                false
            }
            Err(_) => false,
        }
    } else {
        false
    };

    AgentStatus {
        running,
        pid: if running { inner.pid } else { None },
        started_at: if running { inner.started_at } else { None },
        last_error: inner.last_error.clone(),
    }
}

/// Return the last `lines` lines from the agent log file.
#[tauri::command]
fn read_agent_logs_tail(log_path: Option<String>, lines: Option<usize>) -> Vec<String> {
    let path = log_path
        .map(PathBuf::from)
        .unwrap_or_else(default_log_path);

    let n = lines.unwrap_or(80);

    if !path.exists() {
        return vec![format!("[log file not found: {}]", path.display())];
    }

    match std::fs::read_to_string(&path) {
        Ok(content) => {
            let all: Vec<&str> = content.lines().collect();
            let start = all.len().saturating_sub(n);
            all[start..].iter().map(|s| s.to_string()).collect()
        }
        Err(e) => vec![format!("[error reading log: {e}]")],
    }
}

/// Return the resolved default log path (so the UI can show it without hardcoding).
#[tauri::command]
fn get_default_log_path() -> String {
    default_log_path().to_string_lossy().to_string()
}

/// Return the resolved default config path.
#[tauri::command]
fn get_default_config_path() -> String {
    default_config_path().to_string_lossy().to_string()
}

/// Open the logs folder in the OS file manager (Explorer on Windows).
#[tauri::command]
fn open_logs_folder(logs_path: Option<String>) -> Result<(), String> {
    let path = logs_path
        .map(PathBuf::from)
        .unwrap_or_else(default_logs_dir);

    // Ensure the directory exists so Explorer doesn't complain
    let _ = std::fs::create_dir_all(&path);

    open_path_in_os(&path)
}

/// Open the agent config file in the system text editor.
#[tauri::command]
fn open_config_file(config_path: Option<String>) -> Result<(), String> {
    let path = config_path
        .map(PathBuf::from)
        .unwrap_or_else(default_config_path);

    // Create a default config if the file doesn't exist yet
    if !path.exists() {
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let default_content = include_str!("../../../../native/desktop-agent/config.example.toml");
        let _ = std::fs::write(&path, default_content);
    }

    #[cfg(target_os = "windows")]
    {
        Command::new("notepad")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open config in Notepad: {e}"))?;
    }
    #[cfg(not(target_os = "windows"))]
    {
        open_path_in_os(&path)?;
    }

    Ok(())
}

/// Run the agent for N seconds in dry-run mode to test microphone capture.
/// Returns combined stdout output (the agent also writes to its log file).
#[tauri::command]
fn record_mic_test(
    app: AppHandle,
    device_index: Option<i32>,
    device_id: Option<String>,
    device_name: Option<String>,
    duration_sec: Option<i32>,
    save_path: Option<String>,
) -> Result<String, String> {
    let agent = find_agent_exe(&app).ok_or_else(agent_not_found_msg)?;

    let mut cmd_args: Vec<String> = vec![
        "--dry-run".to_string(),
        "--capture-mode".to_string(),
        "microphone".to_string(),
        "--duration-sec".to_string(),
        duration_sec.unwrap_or(10).to_string(),
        "--asr-provider".to_string(),
        "mock".to_string(),
        "--mock-phrase".to_string(),
        "mic test phrase".to_string(),
    ];

    if let Some(idx) = device_index {
        if idx >= 0 {
            cmd_args.extend(["--input-device-index".to_string(), idx.to_string()]);
        }
    }
    if let Some(ref id) = device_id {
        if !id.is_empty() {
            cmd_args.extend(["--input-device-id".to_string(), id.clone()]);
        }
    }
    if let Some(ref name) = device_name {
        if !name.is_empty() {
            cmd_args.extend(["--input-device-name".to_string(), name.clone()]);
        }
    }
    if let Some(ref path) = save_path {
        cmd_args.extend(["--save-chunks".to_string(), path.clone()]);
    }

    let output = Command::new(&agent)
        .args(&cmd_args)
        .output()
        .map_err(|e| format!("Failed to run agent mic test: {e}"))?;

    let mut result = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr);
    if !stderr.is_empty() {
        result.push_str("\n[stderr]\n");
        result.push_str(&stderr);
    }

    Ok(result)
}

// ─── OS open helper ──────────────────────────────────────────────────────────

fn open_path_in_os(path: &PathBuf) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(path)
            .spawn()
            .map_err(|e| format!("Failed to open path: {e}"))?;
    }
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(path)
            .spawn()
            .map_err(|e| format!("Failed to open path: {e}"))?;
    }
    #[cfg(target_os = "linux")]
    {
        Command::new("xdg-open")
            .arg(path)
            .spawn()
            .map_err(|e| format!("Failed to open path: {e}"))?;
    }
    Ok(())
}

// ─── App entry point ─────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AgentManager::default())
        .invoke_handler(tauri::generate_handler![
            list_input_devices,
            write_agent_config,
            start_agent,
            stop_agent,
            agent_status,
            read_agent_logs_tail,
            get_default_log_path,
            get_default_config_path,
            open_logs_folder,
            open_config_file,
            record_mic_test,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
