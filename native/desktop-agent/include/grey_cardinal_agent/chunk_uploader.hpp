#pragma once

#include "grey_cardinal_agent/audio_frame.hpp"
#include "grey_cardinal_agent/config.hpp"
#include "grey_cardinal_agent/http_client.hpp"
#include "grey_cardinal_agent/logger.hpp"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <vector>

namespace grey_cardinal_agent {

class ChunkUploader {
public:
    ChunkUploader(AgentConfig config, Logger& logger);
    ChunkUploader(AgentConfig config, Logger& logger, IHttpClient& http_client);

    void handle_frame(const AudioFrame& frame);
    void flush();

private:
    void flush_unlocked();
    void upload_pcm_chunk(std::vector<std::byte> pcm, const AudioFormat& format);
    std::size_t target_chunk_bytes(const AudioFormat& format) const;

    AgentConfig config_;
    Logger& logger_;
    std::unique_ptr<HttpClient> owned_http_client_;
    IHttpClient* http_client_ = nullptr;
    std::mutex mutex_;
    std::vector<std::byte> buffer_;
    AudioFormat current_format_;
    bool has_format_ = false;
    std::uint64_t next_seq_ = 1;
};

} // namespace grey_cardinal_agent
