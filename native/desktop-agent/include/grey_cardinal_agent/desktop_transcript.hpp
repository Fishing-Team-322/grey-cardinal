#pragma once

#include <string>

namespace grey_cardinal_agent {

struct DesktopTranscriptUpload {
    std::string server_url;
    std::string internal_token;
    std::string user_id;
    std::string device_id;
    std::string client_session_id;
    std::string workspace_id;
    std::string display_name;
    std::string meeting_id;
    std::string microphone_id = "default_input";
    std::string capture_mode = "microphone";
    std::string platform = "windows";
    std::string app_version = "0.1.0";
    std::string text;
    bool is_final = true;
    std::string asr_provider = "mock";
    double asr_confidence = 1.0;
    int duration_ms = 0;
};

std::string build_desktop_transcript_payload(const DesktopTranscriptUpload& upload);

} // namespace grey_cardinal_agent
