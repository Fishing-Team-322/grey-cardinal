#include "grey_cardinal_agent/wav_writer.hpp"

#include <cstdint>
#include <stdexcept>
#include <string_view>

namespace grey_cardinal_agent {
namespace {

void push_ascii(std::vector<std::byte>& out, std::string_view value) {
    for (char ch : value) {
        out.push_back(static_cast<std::byte>(ch));
    }
}

void push_u16(std::vector<std::byte>& out, std::uint16_t value) {
    out.push_back(static_cast<std::byte>(value & 0xff));
    out.push_back(static_cast<std::byte>((value >> 8) & 0xff));
}

void push_u32(std::vector<std::byte>& out, std::uint32_t value) {
    out.push_back(static_cast<std::byte>(value & 0xff));
    out.push_back(static_cast<std::byte>((value >> 8) & 0xff));
    out.push_back(static_cast<std::byte>((value >> 16) & 0xff));
    out.push_back(static_cast<std::byte>((value >> 24) & 0xff));
}

} // namespace

std::vector<std::byte> WavWriter::write_wav(
    const AudioFormat& format,
    const std::vector<std::byte>& pcm
) {
    if (format.sample_rate <= 0 || format.channels <= 0 || format.bits_per_sample <= 0) {
        throw std::runtime_error("invalid audio format for WAV writer");
    }

    const auto data_size = static_cast<std::uint32_t>(pcm.size());
    const auto bytes_per_sample = static_cast<std::uint16_t>(format.bits_per_sample / 8);
    const auto block_align = static_cast<std::uint16_t>(format.channels * bytes_per_sample);
    const auto byte_rate = static_cast<std::uint32_t>(format.sample_rate * block_align);

    std::vector<std::byte> wav;
    wav.reserve(44 + pcm.size());

    push_ascii(wav, "RIFF");
    push_u32(wav, 36 + data_size);
    push_ascii(wav, "WAVE");
    push_ascii(wav, "fmt ");
    push_u32(wav, 16);
    push_u16(wav, 1);
    push_u16(wav, static_cast<std::uint16_t>(format.channels));
    push_u32(wav, static_cast<std::uint32_t>(format.sample_rate));
    push_u32(wav, byte_rate);
    push_u16(wav, block_align);
    push_u16(wav, static_cast<std::uint16_t>(format.bits_per_sample));
    push_ascii(wav, "data");
    push_u32(wav, data_size);
    wav.insert(wav.end(), pcm.begin(), pcm.end());

    return wav;
}

} // namespace grey_cardinal_agent

