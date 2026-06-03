#pragma once

#include "grey_cardinal_agent/audio_frame.hpp"

#include <cstddef>
#include <vector>

namespace grey_cardinal_agent {

double calculate_rms(const AudioFormat& format, const std::vector<std::byte>& pcm);
int duration_ms_for_pcm(const AudioFormat& format, std::size_t pcm_bytes);

} // namespace grey_cardinal_agent
