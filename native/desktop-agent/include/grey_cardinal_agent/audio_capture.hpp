#pragma once

#include "grey_cardinal_agent/audio_frame.hpp"

#include <functional>
#include <string>
#include <vector>

namespace grey_cardinal_agent {

struct AudioDeviceInfo {
    std::string id;
    std::string name;
    bool is_default = false;
};

using AudioFrameCallback = std::function<void(const AudioFrame&)>;

class IAudioCapture {
public:
    virtual ~IAudioCapture() = default;

    virtual std::vector<AudioDeviceInfo> list_devices() = 0;
    virtual void start(AudioFrameCallback callback) = 0;
    virtual void stop() = 0;
};

} // namespace grey_cardinal_agent

