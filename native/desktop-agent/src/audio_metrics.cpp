#include "grey_cardinal_agent/audio_metrics.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>

namespace grey_cardinal_agent {

double calculate_rms(const AudioFormat& format, const std::vector<std::byte>& pcm) {
    if (format.bits_per_sample != 16 || pcm.size() < sizeof(std::int16_t)) {
        return 0.0;
    }

    const std::size_t sample_count = pcm.size() / sizeof(std::int16_t);
    double sum_squares = 0.0;
    for (std::size_t index = 0; index < sample_count; ++index) {
        std::int16_t sample = 0;
        std::memcpy(&sample, pcm.data() + (index * sizeof(std::int16_t)), sizeof(sample));
        const double normalized = static_cast<double>(sample) / 32768.0;
        sum_squares += normalized * normalized;
    }

    return std::sqrt(sum_squares / static_cast<double>(sample_count));
}

int duration_ms_for_pcm(const AudioFormat& format, std::size_t pcm_bytes) {
    const int bytes_per_sample = std::max(1, format.bits_per_sample / 8);
    const int frame_bytes = std::max(1, format.channels * bytes_per_sample);
    if (format.sample_rate <= 0 || frame_bytes <= 0) {
        return 0;
    }
    const double frames = static_cast<double>(pcm_bytes) / static_cast<double>(frame_bytes);
    return static_cast<int>(std::lround((frames * 1000.0) / static_cast<double>(format.sample_rate)));
}

} // namespace grey_cardinal_agent
