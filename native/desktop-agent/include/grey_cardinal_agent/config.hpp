#pragma once

#include <filesystem>
#include <string>

namespace grey_cardinal_agent {

enum class CaptureMode {
    Microphone,
    SystemLoopbackExperimental,
    MixedMeetingExperimental,
    Mock,
};

struct AgentConfig {
    std::string server_url = "http://localhost:8020";
    std::string internal_token;
    std::string meeting_id = "local-windows-demo";
    CaptureMode capture_mode = CaptureMode::Microphone;
    int chunk_ms = 3000;
    int duration_sec = 0;
    std::filesystem::path save_chunks;
    bool dry_run = false;
    bool list_devices = false;
    bool help = false;
    std::filesystem::path config_path;
};

AgentConfig load_config_from_args(int argc, char** argv);
CaptureMode parse_capture_mode(const std::string& value);
std::string capture_mode_value(CaptureMode mode);
std::string config_summary(const AgentConfig& config);
std::string help_text();

} // namespace grey_cardinal_agent
