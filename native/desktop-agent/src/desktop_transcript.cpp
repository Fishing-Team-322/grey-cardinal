#include "grey_cardinal_agent/desktop_transcript.hpp"

#include <iomanip>
#include <sstream>

namespace grey_cardinal_agent {
namespace {

std::string json_escape(const std::string& value) {
    std::ostringstream output;
    for (const unsigned char ch : value) {
        switch (ch) {
        case '"':
            output << "\\\"";
            break;
        case '\\':
            output << "\\\\";
            break;
        case '\b':
            output << "\\b";
            break;
        case '\f':
            output << "\\f";
            break;
        case '\n':
            output << "\\n";
            break;
        case '\r':
            output << "\\r";
            break;
        case '\t':
            output << "\\t";
            break;
        default:
            if (ch < 0x20) {
                output << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                       << static_cast<int>(ch) << std::dec << std::setfill(' ');
            } else {
                output << static_cast<char>(ch);
            }
            break;
        }
    }
    return output.str();
}

void append_json_string(std::ostringstream& output, const std::string& value) {
    output << '"' << json_escape(value) << '"';
}

void append_json_string_or_null(std::ostringstream& output, const std::string& value) {
    if (value.empty()) {
        output << "null";
        return;
    }
    append_json_string(output, value);
}

} // namespace

std::string build_desktop_transcript_payload(const DesktopTranscriptUpload& upload) {
    std::ostringstream output;
    output << "{";
    output << "\"meeting_id\":";
    append_json_string(output, upload.meeting_id);
    output << ",\"workspace_id\":";
    append_json_string_or_null(output, upload.workspace_id);
    output << ",\"source\":{";
    output << "\"kind\":\"desktop_app\"";
    output << ",\"user_id\":";
    append_json_string(output, upload.user_id);
    output << ",\"device_id\":";
    append_json_string(output, upload.device_id);
    output << ",\"client_session_id\":";
    append_json_string(output, upload.client_session_id);
    output << ",\"microphone_id\":";
    append_json_string(output, upload.microphone_id.empty() ? "default_input" : upload.microphone_id);
    output << ",\"capture_mode\":";
    append_json_string(output, upload.capture_mode);
    output << ",\"platform\":";
    append_json_string(output, upload.platform);
    output << ",\"app_version\":";
    append_json_string(output, upload.app_version);
    output << "},\"speaker\":{";
    output << "\"resolved_user_id\":";
    append_json_string(output, upload.user_id);
    output << ",\"resolved_name\":";
    append_json_string(output, upload.display_name);
    output << ",\"identity_source\":\"authenticated_client\"";
    output << ",\"identity_confidence\":1.0";
    output << "},\"text\":";
    append_json_string(output, upload.text);
    output << ",\"is_final\":" << (upload.is_final ? "true" : "false");
    output << ",\"asr\":{";
    output << "\"provider\":";
    append_json_string(output, upload.asr_provider);
    output << ",\"confidence\":" << upload.asr_confidence;
    output << "},\"audio\":{";
    output << "\"source\":";
    append_json_string(output, upload.capture_mode);
    output << ",\"duration_ms\":" << upload.duration_ms;
    output << "},\"raw\":{}";
    output << "}";
    return output.str();
}

} // namespace grey_cardinal_agent
