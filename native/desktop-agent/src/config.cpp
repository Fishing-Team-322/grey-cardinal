#include "grey_cardinal_agent/config.hpp"

#include <cstdlib>
#include <cctype>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <utility>
#include <vector>

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

std::vector<std::string> parse_string_array(const std::string& value) {
    const auto start = value.find('[');
    const auto end = value.rfind(']');
    if (start == std::string::npos || end == std::string::npos || end <= start) {
        throw std::runtime_error("invalid string array value");
    }

    std::vector<std::string> items;
    std::string current;
    bool in_quote = false;
    bool escape = false;

    for (std::size_t index = start + 1; index < end; ++index) {
        const char ch = value[index];
        if (!in_quote) {
            if (ch == '"') {
                in_quote = true;
                current.clear();
            }
            continue;
        }

        if (escape) {
            current.push_back(ch);
            escape = false;
            continue;
        }
        if (ch == '\\') {
            escape = true;
            continue;
        }
        if (ch == '"') {
            in_quote = false;
            items.push_back(current);
            current.clear();
            continue;
        }
        current.push_back(ch);
    }

    if (in_quote) {
        throw std::runtime_error("unterminated string in array value");
    }
    return items;
}

void apply_key_value(AgentConfig& config, const std::string& key, const std::string& raw_value) {
    const std::string value = unquote(raw_value);

    if (key == "brain_api_url" || key == "server_url") {
        config.server_url = value;
    } else if (key == "internal_token") {
        config.internal_token = value;
    } else if (key == "user_id") {
        config.user_id = value;
    } else if (key == "device_id") {
        config.device_id = value;
    } else if (key == "client_session_id") {
        config.client_session_id = value;
    } else if (key == "workspace_id") {
        config.workspace_id = value;
    } else if (key == "display_name") {
        config.display_name = value;
    } else if (key == "meeting_id") {
        config.meeting_id = value;
    } else if (key == "capture_mode") {
        config.capture_mode = parse_capture_mode(value);
    } else if (key == "input_device_id") {
        config.input_device_id = value;
    } else if (key == "chunk_ms") {
        config.chunk_ms = std::stoi(value);
    } else if (key == "asr_provider") {
        config.asr_provider = value;
    } else if (key == "mock_phrases") {
        config.mock_phrases = parse_string_array(raw_value);
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
    std::string array_key;
    std::string array_value;
    while (std::getline(input, line)) {
        const auto comment = line.find('#');
        if (comment != std::string::npos) {
            line = line.substr(0, comment);
        }

        line = trim(std::move(line));
        if (line.empty()) {
            continue;
        }

        if (!array_key.empty()) {
            array_value += " " + line;
            if (line.find(']') != std::string::npos) {
                apply_key_value(config, array_key, array_value);
                array_key.clear();
                array_value.clear();
            }
            continue;
        }

        const auto equals = line.find('=');
        if (equals == std::string::npos) {
            continue;
        }

        const std::string key = trim(line.substr(0, equals));
        const std::string value = trim(line.substr(equals + 1));
        if (value.find('[') != std::string::npos && value.find(']') == std::string::npos) {
            array_key = key;
            array_value = value;
            continue;
        }
        apply_key_value(config, key, value);
    }

    if (!array_key.empty()) {
        throw std::runtime_error("unterminated array value for " + array_key);
    }
}

std::string getenv_or_empty(const char* name) {
    if (const char* value = std::getenv(name)) {
        return value;
    }
    return {};
}

void apply_environment_defaults(AgentConfig& config) {
    if (
        config.config_path.empty() &&
        !getenv_or_empty("GREY_CARDINAL_BRAIN_API_URL").empty()
    ) {
        const std::string url = getenv_or_empty("GREY_CARDINAL_BRAIN_API_URL");
        config.server_url = url;
    }
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
    bool cli_mock_phrases_overridden = false;
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
        } else if (arg == "--server" || arg == "--brain-api-url") {
            config.server_url = require_value(arg);
        } else if (arg == "--token") {
            config.internal_token = require_value(arg);
        } else if (arg == "--user-id") {
            config.user_id = require_value(arg);
        } else if (arg == "--device-id") {
            config.device_id = require_value(arg);
        } else if (arg == "--client-session-id") {
            config.client_session_id = require_value(arg);
        } else if (arg == "--workspace-id") {
            config.workspace_id = require_value(arg);
        } else if (arg == "--display-name") {
            config.display_name = require_value(arg);
        } else if (arg == "--chunk-ms") {
            config.chunk_ms = std::stoi(require_value(arg));
        } else if (arg == "--duration-sec") {
            config.duration_sec = std::stoi(require_value(arg));
        } else if (arg == "--meeting-id") {
            config.meeting_id = require_value(arg);
        } else if (arg == "--capture-mode") {
            config.capture_mode = parse_capture_mode(require_value(arg));
        } else if (arg == "--input-device-id") {
            config.input_device_id = require_value(arg);
        } else if (arg == "--asr-provider") {
            config.asr_provider = require_value(arg);
        } else if (arg == "--mock-phrase") {
            if (!cli_mock_phrases_overridden) {
                config.mock_phrases.clear();
                cli_mock_phrases_overridden = true;
            }
            config.mock_phrases.push_back(require_value(arg));
        } else if (arg == "--save-chunks") {
            config.save_chunks = require_value(arg);
        } else if (arg == "--dry-run" || arg == "--dry-run-save-only") {
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

    if (config.chunk_ms <= 0) {
        throw std::runtime_error("--chunk-ms must be greater than zero");
    }
    if (config.duration_sec < 0) {
        throw std::runtime_error("--duration-sec must be zero or greater");
    }
    if (config.asr_provider.empty()) {
        throw std::runtime_error("asr_provider must not be empty");
    }
    if (config.asr_provider == "mock" && config.mock_phrases.empty()) {
        throw std::runtime_error("mock ASR requires at least one mock phrase");
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

bool has_desktop_identity(const AgentConfig& config) {
    return !config.user_id.empty() &&
           !config.device_id.empty() &&
           !config.client_session_id.empty();
}

std::string config_summary(const AgentConfig& config) {
    std::ostringstream output;
    output << "server_url=" << config.server_url
           << " meeting_id=" << config.meeting_id
           << " capture_mode=" << capture_mode_value(config.capture_mode)
           << " input_device_id=" << (config.input_device_id.empty() ? "<default>" : "<set>")
           << " chunk_ms=" << config.chunk_ms
           << " duration_sec=" << config.duration_sec
           << " asr_provider=" << config.asr_provider
           << " dry_run=" << (config.dry_run ? "true" : "false")
           << " save_chunks=" << (config.save_chunks.empty() ? "<disabled>" : config.save_chunks.string())
           << " token=" << (config.internal_token.empty() ? "<empty>" : "<set>")
           << " desktop_identity=" << (has_desktop_identity(config) ? "<set>" : "<missing>")
           << " config_path=" << (config.config_path.empty() ? "<default-not-found>" : config.config_path.string());
    return output.str();
}

std::string help_text() {
    return R"(Grey Cardinal desktop audio agent

Usage:
  grey-cardinal-agent.exe --config config.toml
  grey-cardinal-agent.exe --server http://localhost:8010 --token dev-internal-token --user-id <uuid> --device-id <uuid> --client-session-id <uuid>
  grey-cardinal-agent.exe --capture-mode microphone --duration-sec 10 --save-chunks C:\Temp\gc-mic --dry-run
  grey-cardinal-agent.exe --list-input-devices

Options:
  --server <url>       brain-api base URL, default http://localhost:8010
  --brain-api-url <url> alias for --server
  --token <token>      internal token, also read from config/env
  --user-id <uuid>     authenticated desktop user id
  --device-id <uuid>   authenticated desktop device id
  --client-session-id <uuid> authenticated desktop client session id
  --workspace-id <uuid-or-empty> optional workspace id
  --display-name <n>   display name used in transcript payload
  --capture-mode <m>   microphone (default), system_loopback_experimental, mixed_meeting_experimental, or mock
  --input-device-id <id> Windows input device id, default input if omitted
  --asr-provider <p>   mock (default); real providers are adapter placeholders
  --mock-phrase <text> replace configured mock phrases; may be repeated
  --chunk-ms <ms>      chunk duration, default 3000
  --duration-sec <s>   capture for N seconds then exit, default 0 means until Ctrl+C
  --meeting-id <id>    meeting id, default MTG-1
  --save-chunks <dir>  write WAV chunks for debugging
  --dry-run            capture and log chunks but skip upload
  --dry-run-save-only  alias for --dry-run, useful with --save-chunks
  --list-input-devices list active Windows input devices
  --config <path>      load simple TOML-style key=value config
  --help               show this help

Default config path:
  %LOCALAPPDATA%\GreyCardinal\Agent\config.toml
)";
}

} // namespace grey_cardinal_agent
