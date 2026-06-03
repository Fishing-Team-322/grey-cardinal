#include "grey_cardinal_agent/asr_provider.hpp"
#include "grey_cardinal_agent/wav_writer.hpp"

#include <algorithm>
#include <array>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace grey_cardinal_agent {

MockAsrProvider::MockAsrProvider(std::vector<std::string> phrases)
    : phrases_(std::move(phrases)) {
    if (phrases_.empty()) {
        throw std::runtime_error("MockAsrProvider requires at least one phrase");
    }
}

AsrResult MockAsrProvider::transcribe(const AsrInput& input) {
    (void)input;
    const std::string& phrase = phrases_[next_index_ % phrases_.size()];
    ++next_index_;
    return {phrase, 1.0};
}

std::string MockAsrProvider::provider_name() const {
    return "mock";
}

FasterWhisperHttpProvider::FasterWhisperHttpProvider(std::string asr_url)
    : asr_url_(std::move(asr_url)) {}

AsrResult FasterWhisperHttpProvider::transcribe(const AsrInput& input) {
    (void)input;
    throw std::runtime_error(
        "faster_whisper_http ASR provider is not implemented in v0. "
        "Configure asr_url and start a faster-whisper HTTP server at: " + asr_url_
    );
}

std::string FasterWhisperHttpProvider::provider_name() const {
    return "faster_whisper_http";
}

WhisperCliProvider::WhisperCliProvider(std::string asr_command)
    : asr_command_(std::move(asr_command)) {
    if (asr_command_.empty()) {
        throw std::runtime_error("WhisperCliProvider requires asr_command");
    }
}

AsrResult WhisperCliProvider::transcribe(const AsrInput& input) {
    (void)input;
    throw std::runtime_error(
        "whisper_cli ASR provider is not implemented in v0. "
        "Configure asr_command with %WAV% placeholder: " + asr_command_
    );
}

std::string WhisperCliProvider::provider_name() const {
    return "whisper_cli";
}

AsrResult SpeechKitProvider::transcribe(const AsrInput& input) {
    (void)input;
    throw std::runtime_error("SpeechKit ASR provider is not implemented in v0");
}

std::string SpeechKitProvider::provider_name() const {
    return "speechkit";
}

} // namespace grey_cardinal_agent
