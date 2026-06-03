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

class FasterWhisperHttpProvider final : public IAsrProvider {
public:
    AsrResult transcribe(const AsrInput& input) override;
    std::string provider_name() const override;
};

class SpeechKitProvider final : public IAsrProvider {
public:
    AsrResult transcribe(const AsrInput& input) override;
    std::string provider_name() const override;
};

} // namespace grey_cardinal_agent
