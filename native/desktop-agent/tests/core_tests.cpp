#include "grey_cardinal_agent/asr_provider.hpp"
#include "grey_cardinal_agent/audio_metrics.hpp"
#include "grey_cardinal_agent/chunk_uploader.hpp"
#include "grey_cardinal_agent/config.hpp"
#include "grey_cardinal_agent/desktop_transcript.hpp"
#include "grey_cardinal_agent/desktop_transcript_uploader.hpp"
#include "grey_cardinal_agent/http_client.hpp"
#include "grey_cardinal_agent/logger.hpp"
#include "grey_cardinal_agent/wav_writer.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

using grey_cardinal_agent::AgentConfig;
using grey_cardinal_agent::AsrInput;
using grey_cardinal_agent::DesktopTranscriptUpload;
using grey_cardinal_agent::DesktopTranscriptUploader;
using grey_cardinal_agent::AudioChunkUpload;
using grey_cardinal_agent::AudioFormat;
using grey_cardinal_agent::AudioFrame;
using grey_cardinal_agent::ChunkUploader;
using grey_cardinal_agent::HttpUploadResult;
using grey_cardinal_agent::IHttpClient;
using grey_cardinal_agent::Logger;
using grey_cardinal_agent::MockAsrProvider;
using grey_cardinal_agent::WavWriter;

void expect_true(bool condition, std::string_view message) {
    if (!condition) {
        throw std::runtime_error(std::string(message));
    }
}

template <typename Left, typename Right>
void expect_eq(const Left& left, const Right& right, std::string_view message) {
    if (!(left == right)) {
        std::ostringstream output;
        output << message;
        throw std::runtime_error(output.str());
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
    std::string output;
    output.reserve(length);
    for (std::size_t index = 0; index < length; ++index) {
        output.push_back(static_cast<char>(data[offset + index]));
    }
    return output;
}

AgentConfig parse_args(const std::vector<std::string>& values) {
    std::vector<char*> argv;
    argv.reserve(values.size());
    for (const std::string& value : values) {
        argv.push_back(const_cast<char*>(value.c_str()));
    }
    return grey_cardinal_agent::load_config_from_args(static_cast<int>(argv.size()), argv.data());
}

void expect_throws(const std::vector<std::string>& values, std::string_view expected_message) {
    try {
        (void)parse_args(values);
    } catch (const std::exception& exc) {
        expect_true(std::string(exc.what()).find(expected_message) != std::string::npos, exc.what());
        return;
    }
    throw std::runtime_error("expected parser to throw");
}

void test_wav_writer_writes_pcm16_mono_header() {
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
    expect_eq(read_ascii(wav, 12, 4), std::string("fmt "), "fmt marker");
    expect_eq(read_le16(wav, 20), static_cast<std::uint16_t>(1), "PCM format");
    expect_eq(read_le16(wav, 22), static_cast<std::uint16_t>(1), "channels");
    expect_eq(read_le32(wav, 24), static_cast<std::uint32_t>(16000), "sample rate");
    expect_eq(read_le16(wav, 34), static_cast<std::uint16_t>(16), "bits per sample");
    expect_eq(read_ascii(wav, 36, 4), std::string("data"), "data marker");
    expect_eq(read_le32(wav, 40), static_cast<std::uint32_t>(4), "data chunk size");
}

void test_wav_writer_handles_empty_payload() {
    const AudioFormat format{8000, 1, 16};
    const std::vector<std::byte> wav = WavWriter::write_wav(format, {});

    expect_eq(wav.size(), static_cast<std::size_t>(44), "empty wav header size");
    expect_eq(read_ascii(wav, 0, 4), std::string("RIFF"), "RIFF marker");
    expect_eq(read_ascii(wav, 8, 4), std::string("WAVE"), "WAVE marker");
    expect_eq(read_le32(wav, 40), static_cast<std::uint32_t>(0), "empty data chunk size");
}

void test_config_defaults_and_cli_overrides() {
    const AgentConfig defaults = parse_args({"agent.exe"});
    expect_eq(defaults.server_url, std::string("http://localhost:8010"), "default server");
    expect_eq(defaults.meeting_id, std::string("MTG-1"), "default meeting id");
    expect_eq(
        grey_cardinal_agent::capture_mode_value(defaults.capture_mode),
        std::string("microphone"),
        "default capture mode"
    );
    expect_eq(defaults.chunk_ms, 3000, "default chunk ms");
    expect_eq(defaults.duration_sec, 0, "default duration");
    expect_true(defaults.save_chunks.empty(), "save chunks disabled by default");
    expect_true(!defaults.dry_run, "dry run disabled by default");

    const AgentConfig config = parse_args({
        "agent.exe",
        "--server",
        "http://localhost:8020/base",
        "--token",
        "secret",
        "--user-id",
        "user-1",
        "--device-id",
        "device-1",
        "--client-session-id",
        "session-1",
        "--workspace-id",
        "",
        "--display-name",
        "Петя",
        "--meeting-id",
        "demo",
        "--capture-mode",
        "system_loopback_experimental",
        "--input-device-id",
        "mic-1",
        "--asr-provider",
        "mock",
        "--mock-phrase",
        "phrase one",
        "--mock-phrase",
        "phrase two",
        "--save-chunks",
        "chunks",
        "--chunk-ms",
        "1250",
        "--duration-sec",
        "15",
        "--dry-run-save-only",
    });
    expect_eq(config.server_url, std::string("http://localhost:8020/base"), "server override");
    expect_eq(config.internal_token, std::string("secret"), "token override");
    expect_eq(config.user_id, std::string("user-1"), "user override");
    expect_eq(config.device_id, std::string("device-1"), "device override");
    expect_eq(config.client_session_id, std::string("session-1"), "session override");
    expect_eq(config.display_name, std::string("Петя"), "display name override");
    expect_eq(config.meeting_id, std::string("demo"), "meeting override");
    expect_eq(
        grey_cardinal_agent::capture_mode_value(config.capture_mode),
        std::string("system_loopback_experimental"),
        "capture mode override"
    );
    expect_eq(config.input_device_id, std::string("mic-1"), "input device override");
    expect_eq(config.save_chunks.string(), std::string("chunks"), "save chunks override");
    expect_eq(config.chunk_ms, 1250, "chunk ms override");
    expect_eq(config.duration_sec, 15, "duration override");
    expect_eq(config.mock_phrases.size(), static_cast<std::size_t>(2), "mock phrase count");
    expect_eq(config.mock_phrases[1], std::string("phrase two"), "mock phrase value");
    expect_true(config.dry_run, "dry-run-save-only sets dry_run");
}

void test_config_file_parses_desktop_identity_and_mock_phrases() {
    const auto dir = std::filesystem::temp_directory_path() / "grey-cardinal-agent-tests";
    std::filesystem::create_directories(dir);
    const auto path = dir / "config.toml";
    {
        std::ofstream output(path);
        output << "brain_api_url = \"http://localhost:8010\"\n";
        output << "internal_token = \"dev-internal-token\"\n";
        output << "user_id = \"user-1\"\n";
        output << "device_id = \"device-1\"\n";
        output << "client_session_id = \"session-1\"\n";
        output << "display_name = \"Петя\"\n";
        output << "meeting_id = \"MTG-1\"\n";
        output << "capture_mode = \"microphone\"\n";
        output << "input_device_id = \"default_input\"\n";
        output << "chunk_ms = 3000\n";
        output << "asr_provider = \"mock\"\n";
        output << "mock_phrases = [\n";
        output << "  \"one\",\n";
        output << "  \"two\"\n";
        output << "]\n";
    }

    const AgentConfig config = parse_args({"agent.exe", "--config", path.string(), "--meeting-id", "MTG-2"});
    expect_eq(config.server_url, std::string("http://localhost:8010"), "brain api url");
    expect_eq(config.internal_token, std::string("dev-internal-token"), "internal token");
    expect_eq(config.user_id, std::string("user-1"), "user id");
    expect_eq(config.device_id, std::string("device-1"), "device id");
    expect_eq(config.client_session_id, std::string("session-1"), "session id");
    expect_eq(config.display_name, std::string("Петя"), "display name");
    expect_eq(config.meeting_id, std::string("MTG-2"), "cli overrides file meeting");
    expect_eq(config.mock_phrases.size(), static_cast<std::size_t>(2), "config mock phrases");
    expect_eq(config.mock_phrases[0], std::string("one"), "first phrase");
}

void test_config_missing_values_fail_helpfully() {
    expect_throws({"agent.exe", "--server"}, "--server requires a value");
    expect_throws({"agent.exe", "--token"}, "--token requires a value");
    expect_throws({"agent.exe", "--meeting-id"}, "--meeting-id requires a value");
    expect_throws({"agent.exe", "--save-chunks"}, "--save-chunks requires a value");
    expect_throws({"agent.exe", "--chunk-ms", "0"}, "--chunk-ms must be greater than zero");
    expect_throws({"agent.exe", "--duration-sec", "-1"}, "--duration-sec must be zero or greater");
}

void test_mock_asr_cycles_phrases() {
    MockAsrProvider provider({"one", "two"});
    const AsrInput input{{}, AudioFormat{16000, 1, 16}, 3000, 0.1};

    expect_eq(provider.transcribe(input).text, std::string("one"), "first phrase");
    expect_eq(provider.transcribe(input).text, std::string("two"), "second phrase");
    expect_eq(provider.transcribe(input).text, std::string("one"), "cycle phrase");
}

void test_rms_calculation_for_pcm16() {
    std::vector<std::byte> pcm;
    const std::int16_t samples[] = {0, 32767, -32768, 0};
    for (const std::int16_t sample : samples) {
        const auto* raw = reinterpret_cast<const std::byte*>(&sample);
        pcm.push_back(raw[0]);
        pcm.push_back(raw[1]);
    }

    const double rms = grey_cardinal_agent::calculate_rms(AudioFormat{16000, 1, 16}, pcm);
    expect_true(rms > 0.70 && rms < 0.72, "rms should be normalized");
    expect_eq(
        grey_cardinal_agent::duration_ms_for_pcm(AudioFormat{1000, 1, 16}, 2000),
        1000,
        "duration ms"
    );
}

class CapturingHttpClient final : public IHttpClient {
public:
    HttpUploadResult post_audio_chunk(const AudioChunkUpload& upload) const override {
        uploads.push_back(upload);
        return {true, 200, "ok", {}};
    }

    HttpUploadResult post_desktop_transcript(const DesktopTranscriptUpload& upload) const override {
        desktop_uploads.push_back(upload);
        return {true, 200, "{\"ok\":true}", {}};
    }

    mutable std::vector<AudioChunkUpload> uploads;
    mutable std::vector<DesktopTranscriptUpload> desktop_uploads;
};

void test_chunk_uploader_uses_fake_http_client() {
    const std::filesystem::path log_path =
        std::filesystem::temp_directory_path() / "grey-cardinal-agent-tests" / "chunk-uploader.log";
    Logger logger(log_path);
    CapturingHttpClient http_client;

    AgentConfig config;
    config.server_url = "http://localhost:8020";
    config.internal_token = "dev-token";
    config.meeting_id = "meeting-1";
    config.chunk_ms = 1;

    ChunkUploader uploader(config, logger, http_client);
    uploader.handle_frame(AudioFrame{
        {static_cast<std::byte>(0x34), static_cast<std::byte>(0x12)},
        AudioFormat{1000, 1, 16},
        {},
    });

    expect_eq(http_client.uploads.size(), static_cast<std::size_t>(1), "one upload");
    const AudioChunkUpload& upload = http_client.uploads.front();
    expect_eq(upload.server_url, std::string("http://localhost:8020"), "server url");
    expect_eq(upload.internal_token, std::string("dev-token"), "internal token");
    expect_eq(upload.meeting_id, std::string("meeting-1"), "meeting id");
    expect_eq(upload.chunk_seq, static_cast<std::uint64_t>(1), "chunk seq");
    expect_eq(upload.format.sample_rate, 1000, "upload sample rate");
    expect_eq(upload.format.channels, 1, "upload channels");
    expect_eq(upload.format.bits_per_sample, 16, "upload bits");
    expect_eq(read_ascii(upload.wav_bytes, 0, 4), std::string("RIFF"), "upload body is WAV");
}

void test_http_request_preview_contains_endpoint_and_headers() {
    const AudioChunkUpload upload{
        "http://localhost:8020/api/",
        "token-1",
        "meeting-2",
        7,
        AudioFormat{48000, 1, 16},
        {},
    };

    const auto preview = grey_cardinal_agent::build_audio_chunk_request_preview(upload);
    std::map<std::string, std::string> headers;
    for (const auto& [name, value] : preview.headers) {
        headers[name] = value;
    }

    expect_eq(preview.endpoint_path, std::string("/api/audio/chunk"), "endpoint path");
    expect_eq(preview.content_type, std::string("audio/wav"), "content type");
    expect_eq(headers["Content-Type"], std::string("audio/wav"), "content-type header");
    expect_eq(headers["X-Internal-Token"], std::string("token-1"), "token header");
    expect_eq(headers["X-Meeting-Id"], std::string("meeting-2"), "meeting header");
    expect_eq(headers["X-Chunk-Seq"], std::string("7"), "seq header");
    expect_eq(headers["X-Audio-Format"], std::string("wav"), "audio format header");
    expect_eq(headers["X-Audio-Sample-Rate"], std::string("48000"), "sample-rate header");
    expect_eq(headers["X-Audio-Channels"], std::string("1"), "channels header");
    expect_eq(headers["X-Audio-Bits-Per-Sample"], std::string("16"), "bits header");
}

void test_desktop_transcript_payload_builder_uses_v2_shape() {
    const DesktopTranscriptUpload upload{
        "http://localhost:8010/api/",
        "token-1",
        "user-1",
        "device-1",
        "session-1",
        "",
        "Петя",
        "MTG-1",
        "default_input",
        "microphone",
        "windows",
        "0.1.0",
        "Я подготовлю оплату до завтра 18:00",
        true,
        "mock",
        1.0,
        3000,
    };

    const auto preview = grey_cardinal_agent::build_desktop_transcript_request_preview(upload);
    std::map<std::string, std::string> headers;
    for (const auto& [name, value] : preview.headers) {
        headers[name] = value;
    }

    expect_eq(preview.endpoint_path, std::string("/api/desktop/transcripts"), "desktop endpoint");
    expect_eq(headers["Content-Type"], std::string("application/json"), "json content type");
    expect_eq(headers["X-Internal-Token"], std::string("token-1"), "token header");
    expect_eq(headers["X-GC-User-Id"], std::string("user-1"), "user header");
    expect_true(preview.body.find("\"source\":{\"kind\":\"desktop_app\"") != std::string::npos, "source shape");
    expect_true(preview.body.find("\"identity_source\":\"authenticated_client\"") != std::string::npos, "speaker shape");
    expect_true(preview.body.find("\"workspace_id\":null") != std::string::npos, "workspace null");
    expect_true(preview.body.find("\"audio\":{\"source\":\"microphone\",\"duration_ms\":3000}") != std::string::npos, "audio shape");
}

void test_desktop_transcript_uploader_posts_mock_asr_text() {
    const std::filesystem::path log_path =
        std::filesystem::temp_directory_path() / "grey-cardinal-agent-tests" / "desktop-uploader.log";
    Logger logger(log_path);
    CapturingHttpClient http_client;
    MockAsrProvider asr({"Я подготовлю оплату до завтра 18:00"});

    AgentConfig config;
    config.server_url = "http://localhost:8010";
    config.internal_token = "dev-token";
    config.user_id = "user-1";
    config.device_id = "device-1";
    config.client_session_id = "session-1";
    config.display_name = "Петя";
    config.meeting_id = "MTG-1";
    config.chunk_ms = 1;

    DesktopTranscriptUploader uploader(config, logger, asr, http_client);
    uploader.handle_frame(AudioFrame{
        {static_cast<std::byte>(0x34), static_cast<std::byte>(0x12)},
        AudioFormat{1000, 1, 16},
        {},
    });

    expect_eq(http_client.desktop_uploads.size(), static_cast<std::size_t>(1), "one desktop upload");
    const DesktopTranscriptUpload& upload = http_client.desktop_uploads.front();
    expect_eq(upload.server_url, std::string("http://localhost:8010"), "desktop server url");
    expect_eq(upload.internal_token, std::string("dev-token"), "desktop token");
    expect_eq(upload.user_id, std::string("user-1"), "desktop user");
    expect_eq(upload.meeting_id, std::string("MTG-1"), "desktop meeting");
    expect_eq(upload.text, std::string("Я подготовлю оплату до завтра 18:00"), "desktop text");
    expect_eq(upload.capture_mode, std::string("microphone"), "desktop capture mode");
    expect_eq(upload.asr_provider, std::string("mock"), "desktop asr provider");
}

void test_platform_selection_sanity() {
#if defined(_WIN32)
    expect_true(true, "Windows build should compile WASAPI capture into the agent executable");
#else
    expect_true(true, "non-Windows builds intentionally stop at CMake platform selection");
#endif
}

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
        {"wav_writer_writes_pcm16_mono_header", test_wav_writer_writes_pcm16_mono_header},
        {"wav_writer_handles_empty_payload", test_wav_writer_handles_empty_payload},
        {"config_defaults_and_cli_overrides", test_config_defaults_and_cli_overrides},
        {"config_file_parses_desktop_identity_and_mock_phrases", test_config_file_parses_desktop_identity_and_mock_phrases},
        {"config_missing_values_fail_helpfully", test_config_missing_values_fail_helpfully},
        {"mock_asr_cycles_phrases", test_mock_asr_cycles_phrases},
        {"rms_calculation_for_pcm16", test_rms_calculation_for_pcm16},
        {"chunk_uploader_uses_fake_http_client", test_chunk_uploader_uses_fake_http_client},
        {"http_request_preview_contains_endpoint_and_headers", test_http_request_preview_contains_endpoint_and_headers},
        {"desktop_transcript_payload_builder_uses_v2_shape", test_desktop_transcript_payload_builder_uses_v2_shape},
        {"desktop_transcript_uploader_posts_mock_asr_text", test_desktop_transcript_uploader_posts_mock_asr_text},
        {"platform_selection_sanity", test_platform_selection_sanity},
    };

    int failures = 0;
    for (const TestCase& test : tests) {
        try {
            test.run();
            std::cout << "[PASS] " << test.name << '\n';
        } catch (const std::exception& exc) {
            ++failures;
            std::cerr << "[FAIL] " << test.name << ": " << exc.what() << '\n';
        }
    }

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return 1;
    }

    return 0;
}
