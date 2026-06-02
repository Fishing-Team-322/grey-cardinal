#pragma once

#include <chrono>
#include <cstddef>
#include <vector>

namespace grey_cardinal_agent {

struct AudioFormat {
    int sample_rate = 0;
    int channels = 0;
    int bits_per_sample = 0;
};

inline bool operator==(const AudioFormat& left, const AudioFormat& right) {
    return left.sample_rate == right.sample_rate &&
           left.channels == right.channels &&
           left.bits_per_sample == right.bits_per_sample;
}

inline bool operator!=(const AudioFormat& left, const AudioFormat& right) {
    return !(left == right);
}

struct AudioFrame {
    std::vector<std::byte> pcm;
    AudioFormat format;
    std::chrono::steady_clock::time_point captured_at;
};

} // namespace grey_cardinal_agent

