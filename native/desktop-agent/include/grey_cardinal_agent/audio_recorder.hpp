#pragma once

#include "grey_cardinal_agent/audio_frame.hpp"
#include "grey_cardinal_agent/config.hpp"
#include "grey_cardinal_agent/logger.hpp"

#include <chrono>
#include <filesystem>
#include <mutex>
#include <vector>

namespace grey_cardinal_agent {

// Accumulates audio frames from the capture callback and writes them as a
// single WAV file when stop() is called.
//
// Usage:
//   recorder.start();
//   capture.start([&](auto& frame) { recorder.handle_frame(frame); });
//   // ... wait ...
//   capture.stop();
//   recorder.stop();
//   auto path = recorder.outputFilePath();  // non-empty if data was recorded
class AudioRecorder {
public:
    AudioRecorder(const AgentConfig& config, Logger& logger);

    // Clears any previous state and marks the start time.
    void start();

    // Called from the audio capture callback (possibly from another thread).
    void handle_frame(const AudioFrame& frame);

    // Finalises recording: writes accumulated PCM to a WAV file.
    // Safe to call multiple times; subsequent calls are no-ops.
    void stop();

    // Path to the WAV file written by stop().
    // Empty if stop() has not been called or no audio was captured.
    std::filesystem::path outputFilePath() const;

    std::chrono::system_clock::time_point startedAt() const;
    std::chrono::system_clock::time_point endedAt() const;

    // Returns true if any PCM data has been buffered.
    bool hasData() const;

private:
    const AgentConfig& config_;
    Logger& logger_;

    mutable std::mutex mutex_;
    std::vector<std::byte> buffer_;
    AudioFormat format_;
    bool has_format_ = false;
    bool stopped_ = false;

    std::filesystem::path output_path_;
    std::chrono::system_clock::time_point started_at_;
    std::chrono::system_clock::time_point ended_at_;
};

} // namespace grey_cardinal_agent
