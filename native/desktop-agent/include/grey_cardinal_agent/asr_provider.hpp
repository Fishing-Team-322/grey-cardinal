#pragma once

#include "grey_cardinal_agent/audio_frame.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace grey_cardinal_agent {

struct AsrInput {
    std::vector<std::byte> pcm;
    AudioFormat format;
    int duration_ms = 0;
    double rms = 0.0;
};

struct AsrResult {
    std::string text;
    double confidence = 0.0;
};

class IAsrProvider {
public:
    virtual ~IAsrProvider() = default;
    virtual AsrResult transcribe(const AsrInput& input) = 0;
    virtual std::string provider_name() const = 0;
};

class MockAsrProvider final : public IAsrProvider {
public:
    explicit MockAsrProvider(std::vector<std::string> phrases);

    AsrResult transcribe(const AsrInput& input) override;
    std::string provider_name() const override;

private:
    std::vector<std::string> phrases_;
    std::size_t next_index_ = 0;
};

// NOTE: faster_whisper_http is an interface stub for demo.
// Configure asr_url to point to a running faster-whisper HTTP server.
// The server must accept: POST /transcribe  Content-Type: audio/wav
// and return: {"text": "...", "confidence": 0.9, "provider": "faster-whisper"}
class FasterWhisperHttpProvider final : public IAsrProvider {
public:
    explicit FasterWhisperHttpProvider(std::string asr_url = "http://localhost:8030/transcribe");
    AsrResult transcribe(const AsrInput& input) override;
    std::string provider_name() const override;
private:
    std::string asr_url_;
};

// NOTE: whisper_cli calls an external command with a WAV file path.
// Configure asr_command with %WAV% as placeholder, e.g.:
//   whisper %WAV% --model base --output-format txt --language ru
class WhisperCliProvider final : public IAsrProvider {
public:
    explicit WhisperCliProvider(std::string asr_command);
    AsrResult transcribe(const AsrInput& input) override;
    std::string provider_name() const override;
private:
    std::string asr_command_;
};

class SpeechKitProvider final : public IAsrProvider {
public:
    AsrResult transcribe(const AsrInput& input) override;
    std::string provider_name() const override;
};

} // namespace grey_cardinal_agent
