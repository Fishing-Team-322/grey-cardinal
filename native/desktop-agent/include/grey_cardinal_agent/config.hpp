#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace grey_cardinal_agent {

enum class CaptureMode {
    Microphone,
    SystemLoopbackExperimental,
    MixedMeetingExperimental,
    Mock,
};

struct AgentConfig {
    std::string server_url = "http://localhost:8010";
    std::string internal_token;
    std::string user_id;
    std::string device_id;
    std::string client_session_id;
    std::string workspace_id;
    std::string display_name;
    std::string meeting_id = "MTG-1";
    CaptureMode capture_mode = CaptureMode::Microphone;
    std::string input_device_id;
    int input_device_index = -1;     // -1 = not set
    std::string input_device_name;   // substring match
    float mic_gain = 1.0f;
    std::string asr_url;      // for faster_whisper_http
    std::string asr_command;  // for whisper_cli
    int chunk_ms = 3000;
    int duration_sec = 0;
    std::string asr_provider = "mock";
    std::vector<std::string> mock_phrases = {
        "Я подготовлю оплату до завтра 18:00",
        "Беру websocket на себя до пятницы",
        "Аня, проверь интеграцию с YouGile сегодня вечером",
    };
    std::filesystem::path save_chunks;
    bool dry_run = false;
    bool list_devices = false;
    bool help = false;
    std::filesystem::path config_path;
};

AgentConfig load_config_from_args(int argc, char** argv);
std::filesystem::path default_config_path();
CaptureMode parse_capture_mode(const std::string& value);
std::string capture_mode_value(CaptureMode mode);
bool has_desktop_identity(const AgentConfig& config);
std::string config_summary(const AgentConfig& config);
std::string help_text();

} // namespace grey_cardinal_agent
