#include "grey_cardinal_agent/audio_recorder.hpp"
#include "grey_cardinal_agent/config.hpp"
#include "grey_cardinal_agent/logger.hpp"
#include "grey_cardinal_agent/uploader.hpp"
#include "grey_cardinal_agent/wav_writer.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

using grey_cardinal_agent::AgentConfig;
using grey_cardinal_agent::AudioFormat;
using grey_cardinal_agent::AudioFrame;
using grey_cardinal_agent::AudioRecorder;
using grey_cardinal_agent::Logger;
using grey_cardinal_agent::WavWriter;

void expect_true(bool condition, std::string_view message) {
    if (!condition) {
        throw std::runtime_error(std::string(message));
    }
}

template <typename Left, typename Right>
void expect_eq(const Left& left, const Right& right, std::string_view message) {
    if (!(left == right)) {
        std::ostringstream out;
        out << message;
        throw std::runtime_error(out.str());
    }
}

std::uint32_t read_le32(const std::vector<std::byte>& data, std::size_t offset) {
    return std::to_integer<std::uint32_t>(data[offset]) |
           (std::to_integer<std::uint32_t>(data[offset + 1]) << 8U) |
           (std::to_integer<std::uint32_t>(data[offset + 2]) << 16U) |
           (std::to_integer<std::uint32_t>(data[offset + 3]) << 24U);
}

std::uint16_t read_le16(const std::vector<std::byte>& data, std::size_t offset) {
    return static_cast<std::uint16_t>(
        std::to_integer<std::uint16_t>(data[offset]) |
        (std::to_integer<std::uint16_t>(data[offset + 1]) << 8U)
    );
}

std::string read_ascii(const std::vector<std::byte>& data, std::size_t offset, std::size_t length) {
    std::string out;
    out.reserve(length);
    for (std::size_t i = 0; i < length; ++i) {
        out.push_back(static_cast<char>(data[offset + i]));
    }
    return out;
}

AgentConfig parse_args(const std::vector<std::string>& values) {
    std::vector<char*> argv;
    argv.reserve(values.size());
    for (const std::string& v : values) {
        argv.push_back(const_cast<char*>(v.c_str()));
    }
    return grey_cardinal_agent::load_config_from_args(static_cast<int>(argv.size()), argv.data());
}

void expect_throws(const std::vector<std::string>& values, std::string_view expected) {
    try {
        (void)parse_args(values);
    } catch (const std::exception& exc) {
        expect_true(std::string(exc.what()).find(expected) != std::string::npos, exc.what());
        return;
    }
    throw std::runtime_error("expected parser to throw");
}

// ── WAV writer ────────────────────────────────────────────────────────────────

void test_wav_writer_pcm16_mono_header() {
    const AudioFormat format{16000, 1, 16};
    const std::vector<std::byte> pcm{
        static_cast<std::byte>(0x01),
        static_cast<std::byte>(0x02),
        static_cast<std::byte>(0x03),
        static_cast<std::byte>(0x04),
    };

    const std::vector<std::byte> wav = WavWriter::write_wav(format, pcm);

    expect_eq(wav.size(), static_cast<std::size_t>(48), "wav size");
    expect_eq(read_ascii(wav, 0, 4), std::string("RIFF"), "RIFF marker");
    expect_eq(read_le32(wav, 4), static_cast<std::uint32_t>(40), "RIFF chunk size");
    expect_eq(read_ascii(wav, 8, 4), std::string("WAVE"), "WAVE marker");
    expect_eq(read_le16(wav, 22), static_cast<std::uint16_t>(1), "channels");
    expect_eq(read_le32(wav, 24), static_cast<std::uint32_t>(16000), "sample rate");
    expect_eq(read_le16(wav, 34), static_cast<std::uint16_t>(16), "bits per sample");
    expect_eq(read_ascii(wav, 36, 4), std::string("data"), "data marker");
    expect_eq(read_le32(wav, 40), static_cast<std::uint32_t>(4), "data chunk size");
}

void test_wav_writer_empty_payload() {
    const AudioFormat format{8000, 1, 16};
    const std::vector<std::byte> wav = WavWriter::write_wav(format, {});
    expect_eq(wav.size(), static_cast<std::size_t>(44), "empty wav size");
    expect_eq(read_le32(wav, 40), static_cast<std::uint32_t>(0), "empty data size");
}

// ── Config ────────────────────────────────────────────────────────────────────

void test_config_defaults() {
    const AgentConfig cfg = parse_args({"agent.exe"});
    expect_eq(cfg.backend_url, std::string("http://localhost:8000"), "default backend");
    expect_eq(cfg.agent_id, std::string("desktop-agent"), "default agent_id");
    expect_true(cfg.meeting_id.empty(), "default meeting_id empty");
    expect_eq(
        grey_cardinal_agent::capture_mode_value(cfg.capture_mode),
        std::string("microphone"),
        "default capture mode"
    );
    expect_eq(cfg.duration_sec, 0, "default duration");
    expect_true(cfg.output_dir.empty(), "default output_dir empty");
    expect_true(!cfg.dry_run, "dry_run off by default");
}

void test_config_cli_overrides() {
    const AgentConfig cfg = parse_args({
        "agent.exe",
        "--backend", "http://server:9000",
        "--agent-id", "agent-42",
        "--meeting-id", "meet-1",
        "--capture-mode", "system_loopback",
        "--input-device-index", "2",
        "--duration-sec", "30",
        "--output-dir", "C:\\recordings",
        "--dry-run",
    });
    expect_eq(cfg.backend_url, std::string("http://server:9000"), "backend override");
    expect_eq(cfg.agent_id, std::string("agent-42"), "agent_id override");
    expect_eq(cfg.meeting_id, std::string("meet-1"), "meeting_id override");
    expect_eq(
        grey_cardinal_agent::capture_mode_value(cfg.capture_mode),
        std::string("system_loopback"),
        "capture mode override"
    );
    expect_eq(cfg.input_device_index, 2, "device index override");
    expect_eq(cfg.duration_sec, 30, "duration override");
    expect_eq(cfg.output_dir.string(), std::string("C:\\recordings"), "output_dir override");
    expect_true(cfg.dry_run, "dry_run override");
}

void test_config_file_parsing() {
    const auto dir = std::filesystem::temp_directory_path() / "grey-cardinal-agent-tests";
    std::filesystem::create_directories(dir);
    const auto path = dir / "config_v2.toml";
    {
        std::ofstream out(path);
        out << "backend_url = \"http://localhost:8010\"\n";
        out << "agent_id = \"agent-001\"\n";
        out << "meeting_id = \"MTG-1\"\n";
        out << "capture_mode = \"microphone\"\n";
        out << "duration_sec = 60\n";
    }
    const AgentConfig cfg = parse_args({"agent.exe", "--config", path.string()});
    expect_eq(cfg.backend_url, std::string("http://localhost:8010"), "config backend");
    expect_eq(cfg.agent_id, std::string("agent-001"), "config agent_id");
    expect_eq(cfg.meeting_id, std::string("MTG-1"), "config meeting_id");
    expect_eq(cfg.duration_sec, 60, "config duration");
}

void test_config_validation_errors() {
    expect_throws({"agent.exe", "--backend"}, "--backend requires a value");
    expect_throws({"agent.exe", "--agent-id"}, "--agent-id requires a value");
    expect_throws({"agent.exe", "--meeting-id"}, "--meeting-id requires a value");
    expect_throws({"agent.exe", "--duration-sec", "-1"}, "--duration-sec must be zero or greater");
    expect_throws({"agent.exe", "--unknown-flag"}, "unknown argument");
}

// ── UUID / ISO 8601 ───────────────────────────────────────────────────────────

void test_generate_uuid_format() {
    const std::string uuid = grey_cardinal_agent::generate_uuid();
    // e.g. "550e8400-e29b-41d4-a716-446655440000"
    expect_eq(uuid.size(), static_cast<std::size_t>(36), "uuid length");
    expect_eq(uuid[8], '-', "uuid dash 1");
    expect_eq(uuid[13], '-', "uuid dash 2");
    expect_eq(uuid[18], '-', "uuid dash 3");
    expect_eq(uuid[23], '-', "uuid dash 4");
}

void test_format_iso8601() {
    // Use a known epoch time: 2024-01-15T10:30:00Z
    std::tm tm{};
    tm.tm_year = 124; // 2024 - 1900
    tm.tm_mon = 0;    // January
    tm.tm_mday = 15;
    tm.tm_hour = 10;
    tm.tm_min = 30;
    tm.tm_sec = 0;
    tm.tm_isdst = 0;
#if defined(_WIN32)
    const std::time_t t = _mkgmtime(&tm);
#else
    const std::time_t t = timegm(&tm);
#endif
    const auto tp = std::chrono::system_clock::from_time_t(t);
    const std::string iso = grey_cardinal_agent::format_iso8601(tp);
    expect_eq(iso, std::string("2024-01-15T10:30:00Z"), "iso8601 format");
}

// ── AudioRecorder ─────────────────────────────────────────────────────────────

void test_audio_recorder_writes_wav_file() {
    const auto log_path =
        std::filesystem::temp_directory_path() / "grey-cardinal-agent-tests" / "recorder.log";
    Logger logger(log_path);

    AgentConfig cfg;
    cfg.output_dir = std::filesystem::temp_directory_path() / "grey-cardinal-agent-tests";

    AudioRecorder recorder(cfg, logger);
    recorder.start();
    expect_true(!recorder.hasData(), "no data before frames");

    // Feed two frames.
    const AudioFormat fmt{16000, 1, 16};
    AudioFrame frame;
    frame.format = fmt;
    frame.pcm = {
        static_cast<std::byte>(0x10), static_cast<std::byte>(0x20),
        static_cast<std::byte>(0x30), static_cast<std::byte>(0x40),
    };
    recorder.handle_frame(frame);
    recorder.handle_frame(frame);

    expect_true(recorder.hasData(), "has data after frames");

    recorder.stop();

    const auto path = recorder.outputFilePath();
    expect_true(!path.empty(), "output path not empty after stop");
    expect_true(std::filesystem::exists(path), "wav file exists on disk");

    // Verify WAV header. Read by size: constructing vector<std::byte> directly
    // from istreambuf_iterator<char> fails under C++20 MSVC (std::construct_at).
    std::ifstream in(path, std::ios::binary);
    in.seekg(0, std::ios::end);
    const std::streamoff wav_size = in.tellg();
    in.seekg(0, std::ios::beg);
    std::vector<std::byte> wav(wav_size > 0 ? static_cast<std::size_t>(wav_size) : 0);
    if (wav_size > 0) {
        in.read(reinterpret_cast<char*>(wav.data()), wav_size);
    }
    expect_true(wav.size() >= 44, "wav file has at least 44 bytes");
    expect_eq(read_ascii(wav, 0, 4), std::string("RIFF"), "RIFF marker");
    expect_eq(read_ascii(wav, 8, 4), std::string("WAVE"), "WAVE marker");

    // Close the file before removing it — Windows blocks deletion of open files.
    in.close();

    // Clean up.
    std::filesystem::remove(path);
}

void test_audio_recorder_stop_without_data() {
    const auto log_path =
        std::filesystem::temp_directory_path() / "grey-cardinal-agent-tests" / "recorder2.log";
    Logger logger(log_path);
    AgentConfig cfg;

    AudioRecorder recorder(cfg, logger);
    recorder.start();
    recorder.stop();

    expect_true(recorder.outputFilePath().empty(), "no output path when no data");
}

// ── Platform ──────────────────────────────────────────────────────────────────

void test_platform_compiles() {
#if defined(_WIN32)
    expect_true(true, "Windows build");
#else
    expect_true(true, "non-Windows build");
#endif
}

// ── Test runner ───────────────────────────────────────────────────────────────

struct TestCase {
    const char* name;
    void (*run)();
};

} // namespace

int main() {
#if defined(_WIN32)
    _putenv_s("GREY_CARDINAL_AGENT_SKIP_DEFAULT_CONFIG", "1");
#else
    setenv("GREY_CARDINAL_AGENT_SKIP_DEFAULT_CONFIG", "1", 1);
#endif

    const std::vector<TestCase> tests{
        {"wav_writer_pcm16_mono_header",   test_wav_writer_pcm16_mono_header},
        {"wav_writer_empty_payload",       test_wav_writer_empty_payload},
        {"config_defaults",                test_config_defaults},
        {"config_cli_overrides",           test_config_cli_overrides},
        {"config_file_parsing",            test_config_file_parsing},
        {"config_validation_errors",       test_config_validation_errors},
        {"generate_uuid_format",           test_generate_uuid_format},
        {"format_iso8601",                 test_format_iso8601},
        {"audio_recorder_writes_wav_file", test_audio_recorder_writes_wav_file},
        {"audio_recorder_stop_no_data",    test_audio_recorder_stop_without_data},
        {"platform_compiles",              test_platform_compiles},
    };

    int failures = 0;
    for (const TestCase& tc : tests) {
        try {
            tc.run();
            std::cout << "[PASS] " << tc.name << '\n';
        } catch (const std::exception& exc) {
            ++failures;
            std::cerr << "[FAIL] " << tc.name << ": " << exc.what() << '\n';
        }
    }

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return 1;
    }
    return 0;
}
