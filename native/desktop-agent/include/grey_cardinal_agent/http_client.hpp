#pragma once

#include "grey_cardinal_agent/audio_frame.hpp"
#include "grey_cardinal_agent/desktop_transcript.hpp"

#include <cstddef>
#include <cstdint>
#include <utility>
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

struct AudioChunkRequestPreview {
    std::string endpoint_path;
    std::vector<std::pair<std::string, std::string>> headers;
    std::string content_type = "audio/wav";
};

AudioChunkRequestPreview build_audio_chunk_request_preview(const AudioChunkUpload& upload);

struct DesktopTranscriptRequestPreview {
    std::string endpoint_path;
    std::vector<std::pair<std::string, std::string>> headers;
    std::string content_type = "application/json";
    std::string body;
};

DesktopTranscriptRequestPreview build_desktop_transcript_request_preview(
    const DesktopTranscriptUpload& upload
);

class IHttpClient {
public:
    virtual ~IHttpClient() = default;
    virtual HttpUploadResult post_audio_chunk(const AudioChunkUpload& upload) const = 0;
    virtual HttpUploadResult post_desktop_transcript(const DesktopTranscriptUpload& upload) const = 0;
};

class HttpClient final : public IHttpClient {
public:
    HttpUploadResult post_audio_chunk(const AudioChunkUpload& upload) const override;
    HttpUploadResult post_desktop_transcript(const DesktopTranscriptUpload& upload) const override;
};

/**
 * Send raw bytes to an arbitrary URL.
 * Used by ASR providers (faster_whisper_http, etc.) to POST WAV audio.
 * This is a free function that does not require an IHttpClient instance.
 */
HttpUploadResult http_post_bytes(
    const std::string& url,
    const std::string& content_type,
    const std::vector<std::byte>& body
);

} // namespace grey_cardinal_agent
