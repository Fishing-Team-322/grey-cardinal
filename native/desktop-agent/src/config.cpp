#include "grey_cardinal_agent/config.hpp"

#include <cstdlib>
#include <cctype>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <utility>
#include <vector>

namespace grey_cardinal_agent {
namespace {

std::string trim(std::string value) {
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

    if (key == "server_url") {
        config.server_url = value;
    } else if (key == "internal_token") {
        config.internal_token = value;
    } else if (key == "meeting_id") {
        config.meeting_id = value;
    } else if (key == "capture_mode") {
        config.capture_mode = parse_capture_mode(value);
    } else if (key == "chunk_ms") {
        config.chunk_ms = std::stoi(value);
    } else if (key == "duration_sec") {
        config.duration_sec = std::stoi(value);
    } else if (key == "save_chunks") {
        config.save_chunks = value;
    } else if (key == "dry_run") {
        config.dry_run = parse_bool(value);
    }
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
        const std::string value = trim(line.substr(equals + 1));
        apply_key_value(config, key, value);
    }
}

std::string getenv_or_empty(const char* name) {
    if (const char* value = std::getenv(name)) {
        return value;
    }
    return {};
}

void apply_environment_defaults(AgentConfig& config) {
    if (config.internal_token.empty()) {
        config.internal_token = getenv_or_empty("GREY_CARDINAL_INTERNAL_TOKEN");
    }
    if (config.internal_token.empty()) {
        config.internal_token = getenv_or_empty("INTERNAL_API_TOKEN");
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
        } else if (arg == "--server") {
            config.server_url = require_value(arg);
        } else if (arg == "--token") {
            config.internal_token = require_value(arg);
        } else if (arg == "--chunk-ms") {
            config.chunk_ms = std::stoi(require_value(arg));
        } else if (arg == "--duration-sec") {
            config.duration_sec = std::stoi(require_value(arg));
        } else if (arg == "--meeting-id") {
            config.meeting_id = require_value(arg);
        } else if (arg == "--capture-mode") {
            config.capture_mode = parse_capture_mode(require_value(arg));
        } else if (arg == "--save-chunks") {
            config.save_chunks = require_value(arg);
        } else if (arg == "--dry-run" || arg == "--dry-run-save-only") {
            config.dry_run = true;
        } else if (arg == "--list-devices") {
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
    }

    apply_environment_defaults(config);
    apply_cli_args(config, args);

    if (config.chunk_ms <= 0) {
        throw std::runtime_error("--chunk-ms must be greater than zero");
    }
    if (config.duration_sec < 0) {
        throw std::runtime_error("--duration-sec must be zero or greater");
    }

    return config;
}

CaptureMode parse_capture_mode(const std::string& value) {
    if (value == "microphone") {
        return CaptureMode::Microphone;
    }
    if (value == "system_loopback_experimental") {
        return CaptureMode::SystemLoopbackExperimental;
    }
    if (value == "mixed_meeting_experimental") {
        return CaptureMode::MixedMeetingExperimental;
    }
    if (value == "mock") {
        return CaptureMode::Mock;
    }
    throw std::runtime_error("unsupported capture mode: " + value);
}

std::string capture_mode_value(CaptureMode mode) {
    switch (mode) {
    case CaptureMode::Microphone:
        return "microphone";
    case CaptureMode::SystemLoopbackExperimental:
        return "system_loopback_experimental";
    case CaptureMode::MixedMeetingExperimental:
        return "mixed_meeting_experimental";
    case CaptureMode::Mock:
        return "mock";
    }
    return "microphone";
}

std::string config_summary(const AgentConfig& config) {
    std::ostringstream output;
    output << "server_url=" << config.server_url
           << " meeting_id=" << config.meeting_id
           << " capture_mode=" << capture_mode_value(config.capture_mode)
           << " chunk_ms=" << config.chunk_ms
           << " duration_sec=" << config.duration_sec
           << " dry_run=" << (config.dry_run ? "true" : "false")
           << " save_chunks=" << (config.save_chunks.empty() ? "<disabled>" : config.save_chunks.string())
           << " token=" << (config.internal_token.empty() ? "<empty>" : "<set>");
    return output.str();
}

std::string help_text() {
    return R"(Grey Cardinal desktop audio agent

Usage:
  grey-cardinal-agent.exe --config config.toml
  grey-cardinal-agent.exe --server http://localhost:8020 --token dev-internal-token
  grey-cardinal-agent.exe --dry-run
  grey-cardinal-agent.exe --save-chunks ./chunks
  grey-cardinal-agent.exe --list-devices

Options:
  --server <url>       audio-worker base URL, default http://localhost:8020
  --token <token>      internal token, also read from config/env
  --capture-mode <m>   microphone (default), system_loopback_experimental, mixed_meeting_experimental, or mock
  --chunk-ms <ms>      chunk duration, default 3000
  --duration-sec <s>   capture for N seconds then exit, default 0 means until Ctrl+C
  --meeting-id <id>    meeting id, default local-windows-demo
  --save-chunks <dir>  write WAV chunks for debugging
  --dry-run            capture and log chunks but skip upload
  --dry-run-save-only  alias for --dry-run, useful with --save-chunks
  --list-devices       list active Windows render devices
  --config <path>      load simple TOML-style key=value config
  --help               show this help
)";
}

} // namespace grey_cardinal_agent
