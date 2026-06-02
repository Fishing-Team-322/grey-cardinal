#pragma once

#include "grey_cardinal_agent/audio_frame.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace grey_cardinal_agent {

struct AudioChunkUpload {
    std::string server_url;
    std::string internal_token;
    std::string meeting_id;
    std::uint64_t chunk_seq = 0;
    AudioFormat format;
    std::vector<std::byte> wav_bytes;
};

struct HttpUploadResult {
    bool ok = false;
    int status_code = 0;
    std::string body;
    std::string error;
};

class HttpClient {
public:
    HttpUploadResult post_audio_chunk(const AudioChunkUpload& upload) const;
};

} // namespace grey_cardinal_agent

