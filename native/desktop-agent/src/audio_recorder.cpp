#include "grey_cardinal_agent/audio_recorder.hpp"
#include "grey_cardinal_agent/wav_writer.hpp"

#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace grey_cardinal_agent {
namespace {

std::filesystem::path make_output_path(
    const AgentConfig& config,
    std::chrono::system_clock::time_point started_at
) {
    const auto time = std::chrono::system_clock::to_time_t(started_at);
    std::tm tm{};
#if defined(_WIN32)
    localtime_s(&tm, &time);
#else
    localtime_r(&time, &tm);
#endif
    std::ostringstream filename;
    filename << "recording_" << std::put_time(&tm, "%Y%m%d_%H%M%S") << ".wav";

    if (!config.output_dir.empty()) {
        std::filesystem::create_directories(config.output_dir);
        return config.output_dir / filename.str();
    }

    // Fall back to system temp directory.
    std::filesystem::path temp_dir;
#if defined(_WIN32)
    if (const char* tmp = std::getenv("TEMP")) {
        temp_dir = std::filesystem::path(tmp) / "grey-cardinal";
    } else if (const char* tmp = std::getenv("TMP")) {
        temp_dir = std::filesystem::path(tmp) / "grey-cardinal";
    } else {
        temp_dir = std::filesystem::temp_directory_path() / "grey-cardinal";
    }
#else
    temp_dir = std::filesystem::temp_directory_path() / "grey-cardinal";
#endif
    std::filesystem::create_directories(temp_dir);
    return temp_dir / filename.str();
}

} // namespace

AudioRecorder::AudioRecorder(const AgentConfig& config, Logger& logger)
    : config_(config), logger_(logger) {}

void AudioRecorder::start() {
    std::lock_guard<std::mutex> lock(mutex_);
    buffer_.clear();
    has_format_ = false;
    stopped_ = false;
    output_path_.clear();
    started_at_ = std::chrono::system_clock::now();
    logger_.info("recorder: started");
}

void AudioRecorder::handle_frame(const AudioFrame& frame) {
    if (frame.pcm.empty()) {
        return;
    }

    std::lock_guard<std::mutex> lock(mutex_);
    if (stopped_) {
        return;
    }

    if (!has_format_) {
        format_ = frame.format;
        has_format_ = true;
        logger_.info(
            "recorder: audio format"
            " sample_rate=" + std::to_string(format_.sample_rate) +
            " channels=" + std::to_string(format_.channels) +
            " bits_per_sample=" + std::to_string(format_.bits_per_sample)
        );
    } else if (frame.format != format_) {
        logger_.warn("recorder: audio format changed mid-recording; ignoring new format");
    }

    buffer_.insert(buffer_.end(), frame.pcm.begin(), frame.pcm.end());
}

void AudioRecorder::stop() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (stopped_) {
        return;
    }
    stopped_ = true;
    ended_at_ = std::chrono::system_clock::now();

    if (!has_format_ || buffer_.empty()) {
        logger_.warn("recorder: stopped with no audio data");
        return;
    }

    output_path_ = make_output_path(config_, started_at_);

    logger_.info(
        "recorder: writing WAV"
        " path=" + output_path_.string() +
        " pcm_bytes=" + std::to_string(buffer_.size())
    );

    const std::vector<std::byte> wav = WavWriter::write_wav(format_, buffer_);

    std::ofstream out(output_path_, std::ios::binary);
    if (!out) {
        logger_.error("recorder: failed to open output file: " + output_path_.string());
        output_path_.clear();
        return;
    }
    out.write(reinterpret_cast<const char*>(wav.data()), static_cast<std::streamsize>(wav.size()));
    out.close();

    logger_.info(
        "recorder: saved"
        " path=" + output_path_.string() +
        " wav_bytes=" + std::to_string(wav.size())
    );
}

std::filesystem::path AudioRecorder::outputFilePath() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return output_path_;
}

std::chrono::system_clock::time_point AudioRecorder::startedAt() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return started_at_;
}

std::chrono::system_clock::time_point AudioRecorder::endedAt() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return ended_at_;
}

bool AudioRecorder::hasData() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return !buffer_.empty() || !output_path_.empty();
}

} // namespace grey_cardinal_agent
