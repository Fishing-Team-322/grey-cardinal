#include "grey_cardinal_agent/desktop_transcript_uploader.hpp"

#include "grey_cardinal_agent/audio_metrics.hpp"
#include "grey_cardinal_agent/wav_writer.hpp"

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <thread>
#include <utility>

namespace grey_cardinal_agent {
namespace {

constexpr double kNearSilentRms = 0.001;

std::string platform_name() {
#if defined(_WIN32)
    return "windows";
#elif defined(__APPLE__)
    return "macos";
#else
    return "linux";
#endif
}

std::string microphone_id_for_config(const AgentConfig& config) {
    if (!config.input_device_id.empty()) {
        return config.input_device_id;
    }
    return "default_input";
}

std::string capture_mode_for_desktop_payload(const AgentConfig& config) {
    if (config.capture_mode == CaptureMode::Mock) {
        return "mock";
    }
    return "microphone";
}

} // namespace

DesktopTranscriptUploader::DesktopTranscriptUploader(
    AgentConfig config,
    Logger& logger,
    IAsrProvider& asr_provider
)
    : config_(std::move(config)),
      logger_(logger),
      asr_provider_(asr_provider),
      owned_http_client_(std::make_unique<HttpClient>()),
      http_client_(owned_http_client_.get()) {}

DesktopTranscriptUploader::DesktopTranscriptUploader(
    AgentConfig config,
    Logger& logger,
    IAsrProvider& asr_provider,
    IHttpClient& http_client
)
    : config_(std::move(config)),
      logger_(logger),
      asr_provider_(asr_provider),
      http_client_(&http_client) {}

void DesktopTranscriptUploader::handle_frame(const AudioFrame& frame) {
    if (frame.pcm.empty()) {
        return;
    }

    std::lock_guard<std::mutex> lock(mutex_);

    if (!has_format_) {
        current_format_ = frame.format;
        has_format_ = true;
        std::ostringstream message;
        message << "audio format sample_rate=" << current_format_.sample_rate
                << " channels=" << current_format_.channels
                << " bits_per_sample=" << current_format_.bits_per_sample;
        logger_.info(message.str());
    } else if (frame.format != current_format_) {
        logger_.warn("audio format changed; flushing current desktop transcript buffer");
        flush_unlocked();
        current_format_ = frame.format;
        has_format_ = true;
    }

    buffer_.insert(buffer_.end(), frame.pcm.begin(), frame.pcm.end());

    const std::size_t target_bytes = target_chunk_bytes(current_format_);
    while (buffer_.size() >= target_bytes) {
        std::vector<std::byte> pcm(
            buffer_.begin(),
            buffer_.begin() + static_cast<std::ptrdiff_t>(target_bytes)
        );
        buffer_.erase(
            buffer_.begin(),
            buffer_.begin() + static_cast<std::ptrdiff_t>(target_bytes)
        );
        process_pcm_chunk(std::move(pcm), current_format_);
    }
}

void DesktopTranscriptUploader::emit_mock_tick() {
    const std::uint64_t seq = next_seq_++;
    const AudioFormat format{16000, 1, 16};
    const AsrResult asr = asr_provider_.transcribe(AsrInput{{}, format, config_.chunk_ms, 0.0});
    std::ostringstream message;
    message << "mock capture tick seq=" << seq << " duration_ms=" << config_.chunk_ms;
    logger_.info(message.str());
    send_transcript(asr, config_.chunk_ms, 0.0, "mock_input");
}

void DesktopTranscriptUploader::flush() {
    std::lock_guard<std::mutex> lock(mutex_);
    flush_unlocked();
}

void DesktopTranscriptUploader::flush_unlocked() {
    if (!buffer_.empty() && has_format_) {
        std::vector<std::byte> pcm;
        pcm.swap(buffer_);
        process_pcm_chunk(std::move(pcm), current_format_);
    }
}

void DesktopTranscriptUploader::process_pcm_chunk(
    std::vector<std::byte> pcm,
    const AudioFormat& format
) {
    const std::uint64_t seq = next_seq_++;
    const double rms = calculate_rms(format, pcm);
    const int duration_ms = duration_ms_for_pcm(format, pcm.size());
    std::vector<std::byte> wav = WavWriter::write_wav(format, pcm);

    if (!config_.save_chunks.empty()) {
        std::filesystem::create_directories(config_.save_chunks);
        std::ostringstream filename;
        filename << "chunk-" << std::setw(6) << std::setfill('0') << seq << ".wav";
        const auto path = config_.save_chunks / filename.str();
        std::ofstream output(path, std::ios::binary);
        output.write(reinterpret_cast<const char*>(wav.data()), static_cast<std::streamsize>(wav.size()));
        logger_.info("saved chunk " + path.string());
    }

    std::ostringstream created;
    created << "desktop chunk created seq=" << seq
            << " wav_bytes=" << wav.size()
            << " duration_ms=" << duration_ms
            << " mic_rms=" << std::fixed << std::setprecision(6) << rms;
    logger_.info(created.str());
    if (rms <= kNearSilentRms) {
        logger_.warn("mic_rms is near zero; check selected microphone, input level, and permissions");
    }

    const AsrResult asr = asr_provider_.transcribe(AsrInput{
        std::move(pcm),
        format,
        duration_ms,
        rms,
    });
    if (asr.text.empty()) {
        logger_.warn("ASR returned empty text; skipping transcript upload");
        return;
    }
    send_transcript(asr, duration_ms, rms, microphone_id_for_config(config_));
}

void DesktopTranscriptUploader::send_transcript(
    const AsrResult& asr,
    int duration_ms,
    double rms,
    const std::string& microphone_id
) {
    if (config_.dry_run) {
        logger_.info("dry-run enabled; skipping desktop transcript upload text=\"" + asr.text + "\"");
        return;
    }

    DesktopTranscriptUpload upload{
        config_.server_url,
        config_.internal_token,
        config_.user_id,
        config_.device_id,
        config_.client_session_id,
        config_.workspace_id,
        config_.display_name,
        config_.meeting_id,
        microphone_id,
        capture_mode_for_desktop_payload(config_),
        platform_name(),
        "0.1.0",
        asr.text,
        true,
        asr_provider_.provider_name(),
        asr.confidence,
        duration_ms,
    };
    (void)rms;

    for (int attempt = 1; attempt <= 3; ++attempt) {
        const HttpUploadResult result = http_client_->post_desktop_transcript(upload);
        if (result.ok) {
            std::ostringstream message;
            message << "desktop transcript upload ok status=" << result.status_code
                    << " body=" << result.body;
            logger_.info(message.str());
            return;
        }

        std::ostringstream message;
        message << "desktop transcript upload failed attempt=" << attempt
                << " status=" << result.status_code
                << " error=" << result.error
                << " body=" << result.body;
        logger_.warn(message.str());

        std::this_thread::sleep_for(std::chrono::milliseconds(250 * attempt));
    }
}

std::size_t DesktopTranscriptUploader::target_chunk_bytes(const AudioFormat& format) const {
    const int bytes_per_sample = std::max(1, format.bits_per_sample / 8);
    const int frame_bytes = std::max(1, format.channels * bytes_per_sample);
    const double bytes_per_ms =
        static_cast<double>(format.sample_rate * frame_bytes) / 1000.0;
    std::size_t target = static_cast<std::size_t>(bytes_per_ms * config_.chunk_ms);
    target = std::max<std::size_t>(target, static_cast<std::size_t>(frame_bytes));
    target -= target % static_cast<std::size_t>(frame_bytes);
    return std::max<std::size_t>(target, static_cast<std::size_t>(frame_bytes));
}

} // namespace grey_cardinal_agent
