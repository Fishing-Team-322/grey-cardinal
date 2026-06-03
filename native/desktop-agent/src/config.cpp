#include "grey_cardinal_agent/config.hpp"

#include <cstdlib>
#include <cctype>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <utility>
#include <vector>

#if defined(_WIN32)
#include <windows.h>
#include <objbase.h>
#else
#include <random>
#endif

namespace grey_cardinal_agent {
namespace {

std::string trim(std::string value) {
    if (value.size() >= 3 &&
        static_cast<unsigned char>(value[0]) == 0xEF &&
        static_cast<unsigned char>(value[1]) == 0xBB &&
        static_cast<unsigned char>(value[2]) == 0xBF) {
        value.erase(0, 3);
    }
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return {};
    }
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

std::string unquote(std::string value) {
    value = trim(std::move(value));
    if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
        return value.substr(1, value.size() - 2);
    }
    return value;
}

bool parse_bool(std::string value) {
    value = trim(std::move(value));
    for (char& ch : value) {
        ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    }
    return value == "1" || value == "true" || value == "yes" || value == "on";
}

void apply_key_value(AgentConfig& config, const std::string& key, const std::string& raw_value) {
    const std::string value = unquote(raw_value);

    if (key == "backend_url" || key == "brain_api_url" || key == "server_url") {
        config.backend_url = value;
    } else if (key == "agent_id") {
        config.agent_id = value;
    } else if (key == "meeting_id") {
        config.meeting_id = value;
    } else if (key == "capture_mode") {
        config.capture_mode = parse_capture_mode(value);
    } else if (key == "input_device_id") {
        config.input_device_id = value;
    } else if (key == "input_device_index") {
        config.input_device_index = std::stoi(value);
    } else if (key == "input_device_name") {
        config.input_device_name = value;
    } else if (key == "duration_sec") {
        config.duration_sec = std::stoi(value);
    } else if (key == "output_dir") {
        config.output_dir = value;
    } else if (key == "dry_run") {
        config.dry_run = parse_bool(value);
    }
    // Unknown keys are silently ignored for forward compatibility.
}

void load_config_file(AgentConfig& config, const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("unable to open config file: " + path.string());
    }

    std::string line;
    while (std::getline(input, line)) {
        const auto comment = line.find('#');
        if (comment != std::string::npos) {
            line = line.substr(0, comment);
        }
        line = trim(std::move(line));
        if (line.empty()) {
            continue;
        }
        const auto equals = line.find('=');
        if (equals == std::string::npos) {
            continue;
        }
        const std::string key = trim(line.substr(0, equals));
        const std::string raw_value = trim(line.substr(equals + 1));
        apply_key_value(config, key, raw_value);
    }
}

std::string getenv_or_empty(const char* name) {
    if (const char* value = std::getenv(name)) {
        return value;
    }
    return {};
}

void apply_environment_defaults(AgentConfig& config) {
    const std::string url = getenv_or_empty("GREY_CARDINAL_BACKEND_URL");
    if (!url.empty() && config.backend_url == "http://localhost:8010") {
        config.backend_url = url;
    }
    const std::string agent_id = getenv_or_empty("GREY_CARDINAL_AGENT_ID");
    if (!agent_id.empty() && config.agent_id == "desktop-agent") {
        config.agent_id = agent_id;
    }
}

std::vector<std::string> args_to_vector(int argc, char** argv) {
    std::vector<std::string> args;
    args.reserve(static_cast<std::size_t>(argc));
    for (int index = 0; index < argc; ++index) {
        args.emplace_back(argv[index]);
    }
    return args;
}

std::filesystem::path find_config_arg(const std::vector<std::string>& args) {
    for (std::size_t index = 1; index < args.size(); ++index) {
        if (args[index] == "--config" && index + 1 < args.size()) {
            return args[index + 1];
        }
    }
    return {};
}

void apply_cli_args(AgentConfig& config, const std::vector<std::string>& args) {
    for (std::size_t index = 1; index < args.size(); ++index) {
        const std::string& arg = args[index];

        auto require_value = [&](const std::string& option) -> std::string {
            if (index + 1 >= args.size()) {
                throw std::runtime_error(option + " requires a value");
            }
            return args[++index];
        };

        if (arg == "--help" || arg == "-h") {
            config.help = true;
        } else if (arg == "--config") {
            config.config_path = require_value(arg);
        } else if (arg == "--backend" || arg == "--backend-url") {
            config.backend_url = require_value(arg);
        } else if (arg == "--agent-id") {
            config.agent_id = require_value(arg);
        } else if (arg == "--meeting-id") {
            config.meeting_id = require_value(arg);
        } else if (arg == "--capture-mode") {
            config.capture_mode = parse_capture_mode(require_value(arg));
        } else if (arg == "--input-device-id") {
            config.input_device_id = require_value(arg);
        } else if (arg == "--input-device-index") {
            config.input_device_index = std::stoi(require_value(arg));
        } else if (arg == "--input-device-name") {
            config.input_device_name = require_value(arg);
        } else if (arg == "--duration-sec") {
            config.duration_sec = std::stoi(require_value(arg));
        } else if (arg == "--output-dir") {
            config.output_dir = require_value(arg);
        } else if (arg == "--dry-run") {
            config.dry_run = true;
        } else if (arg == "--list-input-devices" || arg == "--list-devices") {
            config.list_devices = true;
        } else {
            throw std::runtime_error("unknown argument: " + arg);
        }
    }
}

} // namespace

AgentConfig load_config_from_args(int argc, char** argv) {
    AgentConfig config;
    const std::vector<std::string> args = args_to_vector(argc, argv);

    const auto config_path = find_config_arg(args);
    if (!config_path.empty()) {
        config.config_path = config_path;
        load_config_file(config, config_path);
    } else if (getenv_or_empty("GREY_CARDINAL_AGENT_SKIP_DEFAULT_CONFIG") != "1") {
        const auto path = default_config_path();
        if (!path.empty() && std::filesystem::exists(path)) {
            config.config_path = path;
            load_config_file(config, path);
        }
    }

    apply_environment_defaults(config);
    apply_cli_args(config, args);

    if (config.duration_sec < 0) {
        throw std::runtime_error("--duration-sec must be zero or greater");
    }

    return config;
}

std::filesystem::path default_config_path() {
    if (const char* value = std::getenv("LOCALAPPDATA")) {
        return std::filesystem::path(value) / "GreyCardinal" / "Agent" / "config.toml";
    }
    if (const char* value = std::getenv("HOME")) {
        return std::filesystem::path(value) / ".config" / "grey-cardinal-agent" / "config.toml";
    }
    return {};
}

CaptureMode parse_capture_mode(const std::string& value) {
    if (value == "microphone") {
        return CaptureMode::Microphone;
    }
    if (value == "system_loopback" || value == "system_loopback_experimental") {
        return CaptureMode::SystemLoopback;
    }
    throw std::runtime_error("unsupported capture mode: " + value);
}

std::string capture_mode_value(CaptureMode mode) {
    switch (mode) {
    case CaptureMode::Microphone:
        return "microphone";
    case CaptureMode::SystemLoopback:
        return "system_loopback";
    }
    return "microphone";
}

std::string config_summary(const AgentConfig& config) {
    std::ostringstream output;
    output << "backend_url=" << config.backend_url
           << " agent_id=" << config.agent_id
           << " meeting_id=" << (config.meeting_id.empty() ? "<auto-uuid>" : config.meeting_id)
           << " capture_mode=" << capture_mode_value(config.capture_mode)
           << " input_device_id=" << (config.input_device_id.empty() ? "<default>" : "<set>")
           << " input_device_index=" << config.input_device_index
           << " duration_sec=" << config.duration_sec
           << " output_dir=" << (config.output_dir.empty() ? "<temp>" : config.output_dir.string())
           << " dry_run=" << (config.dry_run ? "true" : "false")
           << " config_path=" << (config.config_path.empty() ? "<default-not-found>" : config.config_path.string());
    return output.str();
}

std::string help_text() {
    return R"(Grey Cardinal desktop audio capture agent

Usage:
  grey-cardinal-agent.exe [options]
  grey-cardinal-agent.exe --config config.toml
  grey-cardinal-agent.exe --backend http://localhost:8010 --agent-id agent-001

Options:
  --backend <url>          Backend base URL (default: http://localhost:8010)
  --backend-url <url>      Alias for --backend
  --agent-id <id>          Agent identifier sent with uploads (default: desktop-agent)
  --meeting-id <id>        Meeting ID; auto-generated UUID if omitted
  --capture-mode <mode>    microphone (default) | system_loopback
  --input-device-id <id>   Select input device by Windows device ID
  --input-device-index <n> Select input device by index (from --list-devices)
  --input-device-name <s>  Select input device by name substring match
  --duration-sec <s>       Record for N seconds then stop (0 = until Ctrl+C)
  --output-dir <dir>       Directory to save WAV files (%TEMP%\grey-cardinal if omitted)
  --dry-run                Record and save WAV, but skip upload
  --list-input-devices     List available Windows input devices and exit
  --list-devices           Alias for --list-input-devices
  --config <path>          Load TOML-style key=value config file
  --help                   Show this help

Default config path:
  %LOCALAPPDATA%\GreyCardinal\Agent\config.toml

Upload endpoint:
  POST {backend_url}/api/audio/upload
  Content-Type: multipart/form-data
  Fields: audio, agent_id, meeting_id, source, started_at, ended_at
)";
}

std::string generate_uuid() {
#if defined(_WIN32)
    GUID guid{};
    CoCreateGuid(&guid);
    char buffer[37];
    snprintf(
        buffer,
        sizeof(buffer),
        "%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x",
        static_cast<unsigned long>(guid.Data1),
        guid.Data2,
        guid.Data3,
        guid.Data4[0], guid.Data4[1],
        guid.Data4[2], guid.Data4[3], guid.Data4[4],
        guid.Data4[5], guid.Data4[6], guid.Data4[7]
    );
    return buffer;
#else
    std::random_device rd;
    std::mt19937 rng(rd());
    std::uniform_int_distribution<std::uint32_t> dist(0, 0xffffffffU);
    char buffer[37];
    const std::uint32_t a = dist(rng);
    const std::uint32_t b = dist(rng);
    const std::uint32_t c = dist(rng);
    const std::uint32_t d = dist(rng);
    snprintf(
        buffer, sizeof(buffer),
        "%08x-%04x-4%03x-8%03x-%04x%08x",
        a, (b >> 16) & 0xffff, b & 0x0fff,
        (c >> 20) & 0x0fff, c & 0xffff, d
    );
    return buffer;
#endif
}

std::string format_iso8601(std::chrono::system_clock::time_point tp) {
    const auto time = std::chrono::system_clock::to_time_t(tp);
    std::tm tm{};
#if defined(_WIN32)
    gmtime_s(&tm, &time);
#else
    gmtime_r(&time, &tm);
#endif
    std::ostringstream ss;
    ss << std::put_time(&tm, "%Y-%m-%dT%H:%M:%SZ");
    return ss.str();
}

} // namespace grey_cardinal_agent
