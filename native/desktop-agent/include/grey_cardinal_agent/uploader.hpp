#pragma once

#include "grey_cardinal_agent/config.hpp"
#include "grey_cardinal_agent/logger.hpp"

#include <filesystem>
#include <string>

namespace grey_cardinal_agent {

struct UploadMetadata {
    std::string agent_id;
    std::string meeting_id;
    std::string started_at;   // ISO 8601 UTC
    std::string ended_at;     // ISO 8601 UTC
};

struct UploadResult {
    bool ok = false;
    std::string audio_id;
    std::string message;
    std::string error;
};

// Posts an audio file to POST {backend_url}/api/audio/upload as multipart/form-data.
// On success: ok=true, audio_id and message are populated.
// On failure: ok=false, error describes what went wrong. The file is preserved.
class Uploader {
public:
    Uploader(const AgentConfig& config, Logger& logger);

    UploadResult uploadAudio(
        const std::filesystem::path& file_path,
        const UploadMetadata& metadata
    );

private:
    const AgentConfig& config_;
    Logger& logger_;
};

} // namespace grey_cardinal_agent
