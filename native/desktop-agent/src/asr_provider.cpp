#include "grey_cardinal_agent/asr_provider.hpp"
#include "grey_cardinal_agent/http_client.hpp"
#include "grey_cardinal_agent/wav_writer.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <utility>

#if defined(_WIN32)
#include <windows.h>
#endif

namespace grey_cardinal_agent {
namespace {

// ── Minimal JSON field extractor ──────────────────────────────────────────────
// Extracts the first value for a key from a flat JSON string.
// Handles: "key": "string value"  and  "key": number
std::string json_extract_string(const std::string& json, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) {
        return {};
    }
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) {
        return {};
    }
    // Skip whitespace
    while (pos + 1 < json.size() && (json[pos + 1] == ' ' || json[pos + 1] == '\t' || json[pos + 1] == '\n')) {
        ++pos;
    }
    ++pos; // skip ':'
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\n')) {
        ++pos;
    }
    if (pos >= json.size()) {
        return {};
    }
    if (json[pos] == '"') {
        // String value
        ++pos;
        std::string result;
        for (; pos < json.size(); ++pos) {
            if (json[pos] == '\\' && pos + 1 < json.size()) {
                ++pos;
                result.push_back(json[pos]);
            } else if (json[pos] == '"') {
                break;
            } else {
                result.push_back(json[pos]);
            }
        }
        return result;
    }
    // Numeric or other value — read until delimiter
    std::size_t end = pos;
    while (end < json.size() && json[end] != ',' && json[end] != '}' && json[end] != ']' && json[end] != '\n') {
        ++end;
    }
    std::string token = json.substr(pos, end - pos);
    // Trim trailing whitespace
    while (!token.empty() && (token.back() == ' ' || token.back() == '\r' || token.back() == '\t')) {
        token.pop_back();
    }
    return token;
}

// ── Temp file helper ──────────────────────────────────────────────────────────

std::filesystem::path write_temp_wav(const std::vector<std::byte>& wav_bytes) {
#if defined(_WIN32)
    char temp_dir[MAX_PATH] = {};
    GetTempPathA(MAX_PATH, temp_dir);
    char temp_file[MAX_PATH] = {};
    GetTempFileNameA(temp_dir, "gcasr", 0, temp_file);
    // GetTempFileName creates the file; overwrite it.
    std::filesystem::path path(temp_file);
    // Rename to .wav so whisper recognises the format by extension
    const auto wav_path = path.parent_path() / (path.stem().string() + ".wav");
    std::ofstream out(wav_path, std::ios::binary);
    out.write(reinterpret_cast<const char*>(wav_bytes.data()),
              static_cast<std::streamsize>(wav_bytes.size()));
    // Remove the placeholder file created by GetTempFileName
    std::error_code ec;
    std::filesystem::remove(path, ec);
    return wav_path;
#else
    const std::string tmpl = "/tmp/gcasr_XXXXXX.wav";
    // Use mkstemp-style: mkstemps gives us a .wav suffix on supported systems.
    char name[64];
    std::snprintf(name, sizeof(name), "/tmp/gcasr_%d.wav", static_cast<int>(getpid()));
    std::ofstream out(name, std::ios::binary);
    out.write(reinterpret_cast<const char*>(wav_bytes.data()),
              static_cast<std::streamsize>(wav_bytes.size()));
    return std::filesystem::path(name);
#endif
}

// ── Subprocess stdout reader (for whisper_cli) ────────────────────────────────

std::string run_command_capture_stdout(const std::string& command) {
#if defined(_WIN32)
    FILE* pipe = _popen(command.c_str(), "r");
    if (pipe == nullptr) {
        throw std::runtime_error("failed to run command: " + command);
    }
#else
    FILE* pipe = popen(command.c_str(), "r");
    if (pipe == nullptr) {
        throw std::runtime_error("failed to run command: " + command);
    }
#endif
    std::string output;
    std::array<char, 512> buf{};
    while (std::fgets(buf.data(), static_cast<int>(buf.size()), pipe) != nullptr) {
        output += buf.data();
    }
#if defined(_WIN32)
    _pclose(pipe);
#else
    pclose(pipe);
#endif
    return output;
}

} // namespace

// ── MockAsrProvider ───────────────────────────────────────────────────────────

MockAsrProvider::MockAsrProvider(std::vector<std::string> phrases)
    : phrases_(std::move(phrases)) {
    if (phrases_.empty()) {
        throw std::runtime_error("MockAsrProvider requires at least one phrase");
    }
}

AsrResult MockAsrProvider::transcribe(const AsrInput& input) {
    (void)input;
    const std::string& phrase = phrases_[next_index_ % phrases_.size()];
    ++next_index_;
    return {phrase, 1.0};
}

std::string MockAsrProvider::provider_name() const {
    return "mock";
}

// ── FasterWhisperHttpProvider ─────────────────────────────────────────────────

FasterWhisperHttpProvider::FasterWhisperHttpProvider(std::string asr_url)
    : asr_url_(std::move(asr_url)) {}

AsrResult FasterWhisperHttpProvider::transcribe(const AsrInput& input) {
    // Build WAV bytes from raw PCM
    const std::vector<std::byte> wav = WavWriter::write_wav(input.format, input.pcm);
    if (wav.empty()) {
        return {"", 0.0};
    }

    const HttpUploadResult result = http_post_bytes(asr_url_, "audio/wav", wav);

    if (!result.ok) {
        throw std::runtime_error(
            "faster_whisper_http POST to " + asr_url_ +
            " failed: " + result.error +
            " (status " + std::to_string(result.status_code) + ")"
            " body=" + result.body
        );
    }

    // Parse {"text": "...", "confidence": 0.9}
    const std::string text = json_extract_string(result.body, "text");
    const std::string confidence_str = json_extract_string(result.body, "confidence");

    double confidence = 0.8;
    if (!confidence_str.empty()) {
        try {
            confidence = std::stod(confidence_str);
        } catch (...) {}
    }

    return {text, confidence};
}

std::string FasterWhisperHttpProvider::provider_name() const {
    return "faster_whisper_http";
}

// ── WhisperCliProvider ────────────────────────────────────────────────────────

WhisperCliProvider::WhisperCliProvider(std::string asr_command)
    : asr_command_(std::move(asr_command)) {
    if (asr_command_.empty()) {
        throw std::runtime_error("WhisperCliProvider requires asr_command");
    }
}

AsrResult WhisperCliProvider::transcribe(const AsrInput& input) {
    // Write WAV to a temp file
    const std::vector<std::byte> wav = WavWriter::write_wav(input.format, input.pcm);
    const std::filesystem::path wav_path = write_temp_wav(wav);
    const std::string wav_str = wav_path.string();

    // Replace %WAV% placeholder with the actual path
    std::string command = asr_command_;
    const std::string placeholder = "%WAV%";
    std::string::size_type pos = 0;
    while ((pos = command.find(placeholder, pos)) != std::string::npos) {
        command.replace(pos, placeholder.size(), wav_str);
        pos += wav_str.size();
    }
    if (command == asr_command_) {
        // No placeholder found — append path as a positional argument
        command += " \"" + wav_str + "\"";
    }

    std::string output;
    std::error_code ec;
    try {
        output = run_command_capture_stdout(command);
    } catch (const std::exception& exc) {
        std::filesystem::remove(wav_path, ec);
        throw std::runtime_error(
            std::string("whisper_cli failed: ") + exc.what() +
            " (command: " + command + ")"
        );
    }

    std::filesystem::remove(wav_path, ec);

    // Trim whitespace
    const auto first = output.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return {"", 0.8};
    }
    const auto last = output.find_last_not_of(" \t\r\n");
    const std::string text = output.substr(first, last - first + 1);

    return {text, 0.8};
}

std::string WhisperCliProvider::provider_name() const {
    return "whisper_cli";
}

// ── SpeechKitProvider ─────────────────────────────────────────────────────────

AsrResult SpeechKitProvider::transcribe(const AsrInput& input) {
    (void)input;
    throw std::runtime_error("SpeechKit ASR provider is not implemented in v0");
}

std::string SpeechKitProvider::provider_name() const {
    return "speechkit";
}

} // namespace grey_cardinal_agent
