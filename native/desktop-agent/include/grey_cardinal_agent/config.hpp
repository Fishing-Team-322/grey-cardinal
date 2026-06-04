#pragma once

#include <chrono>
#include <filesystem>
#include <string>

namespace grey_cardinal_agent {

enum class CaptureMode {
    Microphone,
    SystemLoopback,
};

struct AgentConfig {
    // Backend endpoint (brain-api), e.g. http://localhost:8000
    std::string backend_url = "http://localhost:8000";

    // Identifies this agent instance to the backend.
    std::string agent_id = "desktop-agent";

    // --- Account pairing (set by the tray "Pair device" flow) ---
    // Human-readable device name shown in the cockpit agents list.
    std::string device_name;
    // Workspace this daemon is bound to (returned by /api/agents/register).
    std::string workspace_id;
    // Per-device bearer token issued at pairing; sent as X-Agent-Token on
    // heartbeat/upload. Stored locally only — never shipped in the installer.
    std::string agent_token;

    // Meeting ID sent with the upload.
    // Auto-generated UUID if left empty.
    std::string meeting_id;

    // Audio capture source.
    CaptureMode capture_mode = CaptureMode::Microphone;

    // Optional input device selection (Windows only).
    std::string input_device_id;
    int input_device_index = -1;      // 0-based index from --list-devices
    std::string input_device_name;    // substring match

    // Record for N seconds then stop. 0 = run until Ctrl+C.
    int duration_sec = 0;

    // Directory where WAV files are saved after recording.
    // Uses %TEMP%\grey-cardinal if empty.
    std::filesystem::path output_dir;

    // If true: record and save WAV, but skip the upload.
    bool dry_run = false;

    // If true: print device list and exit.
    bool list_devices = false;

    bool help = false;
    std::filesystem::path config_path;
};

AgentConfig load_config_from_args(int argc, char** argv);
std::filesystem::path default_config_path();
CaptureMode parse_capture_mode(const std::string& value);
std::string capture_mode_value(CaptureMode mode);
std::string config_summary(const AgentConfig& config);
std::string help_text();

// Generate a random UUID v4 string.
std::string generate_uuid();

// Format a time_point as ISO 8601 UTC string.
std::string format_iso8601(std::chrono::system_clock::time_point tp);

} // namespace grey_cardinal_agent
