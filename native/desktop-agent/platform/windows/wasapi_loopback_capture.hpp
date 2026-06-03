#pragma once

#include "grey_cardinal_agent/audio_capture.hpp"

#include <atomic>
#include <string>
#include <thread>

namespace grey_cardinal_agent {

enum class WindowsWasapiEndpointKind {
    InputMicrophone,
    RenderLoopback,
};

class WindowsWasapiCapture final : public IAudioCapture {
public:
    explicit WindowsWasapiCapture(
        WindowsWasapiEndpointKind endpoint_kind,
        std::string device_id = {},
        int device_index = -1,
        std::string device_name_substr = {}
    );
    ~WindowsWasapiCapture() override;

    WindowsWasapiCapture(const WindowsWasapiCapture&) = delete;
    WindowsWasapiCapture& operator=(const WindowsWasapiCapture&) = delete;

    std::vector<AudioDeviceInfo> list_devices() override;
    void start(AudioFrameCallback callback) override;
    void stop() override;

private:
    void capture_loop(AudioFrameCallback callback);

    WindowsWasapiEndpointKind endpoint_kind_;
    std::string device_id_;
    int device_index_;
    std::string device_name_substr_;
    std::atomic_bool running_{false};
    std::thread worker_;
};

} // namespace grey_cardinal_agent

