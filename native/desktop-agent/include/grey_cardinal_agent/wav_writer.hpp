#pragma once

#include "grey_cardinal_agent/audio_frame.hpp"

#include <cstddef>
#include <vector>

namespace grey_cardinal_agent {

class WavWriter {
public:
    static std::vector<std::byte> write_wav(
        const AudioFormat& format,
        const std::vector<std::byte>& pcm
    );
};

} // namespace grey_cardinal_agent

