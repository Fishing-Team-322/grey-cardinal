#pragma once

#include "grey_cardinal_agent/audio_capture.hpp"

#include <atomic>
#include <thread>

namespace grey_cardinal_agent {

class WindowsWasapiLoopbackCapture final : public IAudioCapture {
public:
    WindowsWasapiLoopbackCapture() = default;
    ~WindowsWasapiLoopbackCapture() override;

    WindowsWasapiLoopbackCapture(const WindowsWasapiLoopbackCapture&) = delete;
    WindowsWasapiLoopbackCapture& operator=(const WindowsWasapiLoopbackCapture&) = delete;

    std::vector<AudioDeviceInfo> list_devices() override;
    void start(AudioFrameCallback callback) override;
    void stop() override;

private:
    void capture_loop(AudioFrameCallback callback);

    std::atomic_bool running_{false};
    std::thread worker_;
};

} // namespace grey_cardinal_agent

