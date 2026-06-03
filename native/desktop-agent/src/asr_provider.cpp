#include "grey_cardinal_agent/asr_provider.hpp"

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

AsrResult FasterWhisperHttpProvider::transcribe(const AsrInput& input) {
    (void)input;
    throw std::runtime_error("faster-whisper HTTP ASR provider is not implemented in v0");
}

std::string FasterWhisperHttpProvider::provider_name() const {
    return "faster_whisper_http";
}

AsrResult SpeechKitProvider::transcribe(const AsrInput& input) {
    (void)input;
    throw std::runtime_error("SpeechKit ASR provider is not implemented in v0");
}

std::string SpeechKitProvider::provider_name() const {
    return "speechkit";
}

} // namespace grey_cardinal_agent
