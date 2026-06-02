#pragma once

#include "grey_cardinal_agent/audio_capture.hpp"

#include <stdexcept>

namespace grey_cardinal_agent {

class LinuxPipeWireAudioCapture final : public IAudioCapture {
public:
    std::vector<AudioDeviceInfo> list_devices() override {
        throw std::runtime_error("Linux PipeWire/PulseAudio monitor capture adapter is not implemented yet");
    }

    void start(AudioFrameCallback callback) override {
        (void)callback;
        throw std::runtime_error("Linux PipeWire/PulseAudio monitor capture adapter is not implemented yet");
    }

    void stop() override {}
};

} // namespace grey_cardinal_agent

