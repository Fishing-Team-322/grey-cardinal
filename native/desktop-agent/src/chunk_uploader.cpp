#include "grey_cardinal_agent/chunk_uploader.hpp"

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

ChunkUploader::ChunkUploader(AgentConfig config, Logger& logger)
    : config_(std::move(config)), logger_(logger) {}

void ChunkUploader::handle_frame(const AudioFrame& frame) {
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
        logger_.warn("audio format changed; flushing current chunk buffer");
        flush_unlocked();
        current_format_ = frame.format;
        has_format_ = true;
    }

    buffer_.insert(buffer_.end(), frame.pcm.begin(), frame.pcm.end());

    const std::size_t target_bytes = target_chunk_bytes(current_format_);
    while (buffer_.size() >= target_bytes) {
        std::vector<std::byte> pcm(buffer_.begin(), buffer_.begin() + static_cast<std::ptrdiff_t>(target_bytes));
        buffer_.erase(buffer_.begin(), buffer_.begin() + static_cast<std::ptrdiff_t>(target_bytes));
        upload_pcm_chunk(std::move(pcm), current_format_);
    }
}

void ChunkUploader::flush() {
    std::lock_guard<std::mutex> lock(mutex_);
    flush_unlocked();
}

void ChunkUploader::flush_unlocked() {
    if (!buffer_.empty() && has_format_) {
        std::vector<std::byte> pcm;
        pcm.swap(buffer_);
        upload_pcm_chunk(std::move(pcm), current_format_);
    }
}

void ChunkUploader::upload_pcm_chunk(std::vector<std::byte> pcm, const AudioFormat& format) {
    const std::uint64_t seq = next_seq_++;
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
    created << "chunk created seq=" << seq << " wav_bytes=" << wav.size();
    logger_.info(created.str());

    if (config_.dry_run) {
        logger_.info("dry-run enabled; skipping upload");
        return;
    }

    AudioChunkUpload upload{
        config_.server_url,
        config_.internal_token,
        config_.meeting_id,
        seq,
        format,
        std::move(wav)
    };

    for (int attempt = 1; attempt <= 3; ++attempt) {
        const HttpUploadResult result = http_client_.post_audio_chunk(upload);
        if (result.ok) {
            std::ostringstream message;
            message << "upload ok seq=" << seq << " status=" << result.status_code
                    << " body=" << result.body;
            logger_.info(message.str());
            return;
        }

        std::ostringstream message;
        message << "upload failed seq=" << seq << " attempt=" << attempt
                << " status=" << result.status_code << " error=" << result.error;
        logger_.warn(message.str());

        std::this_thread::sleep_for(std::chrono::milliseconds(250 * attempt));
    }
}

std::size_t ChunkUploader::target_chunk_bytes(const AudioFormat& format) const {
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
