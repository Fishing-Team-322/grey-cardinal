#include "grey_cardinal_agent/asr_provider.hpp"
#include "grey_cardinal_agent/chunk_uploader.hpp"
#include "grey_cardinal_agent/config.hpp"
#include "grey_cardinal_agent/desktop_transcript_uploader.hpp"
#include "grey_cardinal_agent/logger.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <exception>
#include <iostream>
#include <memory>
#include <thread>

#if defined(_WIN32)
#include "wasapi_loopback_capture.hpp"
#endif

namespace {

std::atomic_bool g_stop_requested{false};

void handle_signal(int) {
    g_stop_requested = true;
}

std::unique_ptr<grey_cardinal_agent::IAsrProvider> make_asr_provider(
    const grey_cardinal_agent::AgentConfig& config
) {
    using namespace grey_cardinal_agent;
    if (config.asr_provider == "mock") {
        return std::make_unique<MockAsrProvider>(config.mock_phrases);
    }
    if (config.asr_provider == "faster_whisper_http") {
        const std::string url = config.asr_url.empty()
            ? "http://localhost:8030/transcribe"
            : config.asr_url;
        return std::make_unique<FasterWhisperHttpProvider>(url);
    }
    if (config.asr_provider == "whisper_cli") {
        return std::make_unique<WhisperCliProvider>(config.asr_command);
    }
    if (config.asr_provider == "speechkit") {
        return std::make_unique<SpeechKitProvider>();
    }
    throw std::runtime_error("unsupported ASR provider: " + config.asr_provider);
}

bool desktop_upload_config_is_valid(
    const grey_cardinal_agent::AgentConfig& config,
    grey_cardinal_agent::Logger& logger
) {
    if (config.dry_run) {
        return true;
    }
    bool ok = true;
    if (config.internal_token.empty()) {
        logger.error("internal token is required for desktop transcript uploads");
        ok = false;
    }
    if (!grey_cardinal_agent::has_desktop_identity(config)) {
        logger.error("user_id, device_id, and client_session_id are required for desktop transcript uploads");
        ok = false;
    }
    if (config.display_name.empty()) {
        logger.warn("display_name is empty; server will still resolve identity from headers");
    }
    return ok;
}

} // namespace

int main(int argc, char** argv) {
    using namespace grey_cardinal_agent;

    try {
        AgentConfig config = load_config_from_args(argc, argv);
        if (config.help) {
            std::cout << help_text();
            return 0;
        }

        Logger logger(Logger::default_log_path());
        logger.info("Grey Cardinal desktop agent starting");
        logger.info("log_file=" + logger.path().string());
        logger.info("config " + config_summary(config));
        if (config.asr_provider == "mock") {
            logger.warn(
                "ASR: mock -- transcripts are simulated phrases, not real speech recognition. "
                "Set asr_provider=faster_whisper_http or whisper_cli for real ASR."
            );
        } else {
            logger.info("ASR: " + config.asr_provider);
        }

        if (config.capture_mode == CaptureMode::MixedMeetingExperimental) {
            logger.warn("mixed_meeting_experimental is not implemented in v0");
            std::cerr << "capture mode mixed_meeting_experimental is not implemented in v0\n";
            return 2;
        }

#if defined(_WIN32)
        WindowsWasapiEndpointKind endpoint_kind =
            config.capture_mode == CaptureMode::SystemLoopbackExperimental
                ? WindowsWasapiEndpointKind::RenderLoopback
                : WindowsWasapiEndpointKind::InputMicrophone;
        WindowsWasapiCapture capture(
            endpoint_kind,
            config.input_device_id,
            config.input_device_index,
            config.input_device_name
        );
        const auto devices = capture.list_devices();
        if (config.list_devices) {
            std::cout << "Input devices:\n";
            for (const auto& device : devices) {
                const char* marker = device.is_default ? "* " : "  ";
                std::cout << marker << "[" << device.index << "] ";
                if (!device.role.empty()) {
                    std::cout << device.role << ": ";
                }
                std::cout << device.name << "\n"
                          << "    id: " << device.id << "\n";
                if (!device.role.empty()) {
                    std::cout << "    role: " << device.role << "\n";
                }
            }
            return 0;
        }
#else
        if (config.list_devices) {
            std::cerr << "device listing is not implemented for this platform yet\n";
            return 2;
        }
        std::cerr << "desktop agent capture is not implemented for this platform yet\n";
        return 2;
#endif

        std::signal(SIGINT, handle_signal);
        std::signal(SIGTERM, handle_signal);

        const auto started_at = std::chrono::steady_clock::now();

        if (config.capture_mode == CaptureMode::SystemLoopbackExperimental) {
            logger.warn(
                "system_loopback_experimental is legacy/dev only and is not trusted for desktop speaker identity"
            );
            for (const auto& device : devices) {
                if (device.is_default) {
                    logger.info("selected render loopback device " + device.name);
                    break;
                }
            }
            ChunkUploader uploader(config, logger);
            capture.start([&uploader](const AudioFrame& frame) {
                uploader.handle_frame(frame);
            });

            logger.info("loopback capture started; press Ctrl+C to stop");
            while (!g_stop_requested) {
                if (config.duration_sec > 0) {
                    const auto elapsed = std::chrono::steady_clock::now() - started_at;
                    if (elapsed >= std::chrono::seconds(config.duration_sec)) {
                        logger.info("duration reached; stopping capture");
                        break;
                    }
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(250));
            }

            logger.info("stopping loopback capture");
            capture.stop();
            uploader.flush();
        } else {
            if (!desktop_upload_config_is_valid(config, logger)) {
                return 2;
            }
            auto asr_provider = make_asr_provider(config);
            DesktopTranscriptUploader uploader(config, logger, *asr_provider);

            if (config.capture_mode == CaptureMode::Mock) {
                logger.warn(
                    "mock capture mode uses no audio and is for development only; "
                    "use capture_mode=microphone with asr_provider=mock for trusted v0"
                );
                logger.info("mock capture started; press Ctrl+C to stop");
                while (!g_stop_requested) {
                    if (config.duration_sec > 0) {
                        const auto elapsed = std::chrono::steady_clock::now() - started_at;
                        if (elapsed >= std::chrono::seconds(config.duration_sec)) {
                            logger.info("duration reached; stopping mock capture");
                            break;
                        }
                    }
                    uploader.emit_mock_tick();
                    std::this_thread::sleep_for(std::chrono::milliseconds(config.chunk_ms));
                }
            } else {
                for (const auto& device : devices) {
                    if (device.is_default_communications || device.is_default) {
                        logger.info("selected_input_device_name=" + device.name);
                        logger.info("selected_input_device_id=" + device.id);
                        logger.info("selected_input_device_role=" + (device.role.empty() ? "default" : device.role));
                        logger.info("mic_gain=" + std::to_string(config.mic_gain));
                        break;
                    }
                }
                if (!config.input_device_id.empty()) {
                    logger.info("selected_input_device_id=<explicit:" + config.input_device_id + ">");
                } else if (config.input_device_index >= 0) {
                    logger.info("selected_input_device_index=" + std::to_string(config.input_device_index));
                } else if (!config.input_device_name.empty()) {
                    logger.info("selected_input_device_name_filter=" + config.input_device_name);
                }
                capture.start([&uploader](const AudioFrame& frame) {
                    uploader.handle_frame(frame);
                });

                logger.info("microphone capture started; press Ctrl+C to stop");
                while (!g_stop_requested) {
                    if (config.duration_sec > 0) {
                        const auto elapsed = std::chrono::steady_clock::now() - started_at;
                        if (elapsed >= std::chrono::seconds(config.duration_sec)) {
                            logger.info("duration reached; stopping microphone capture");
                            break;
                        }
                    }
                    std::this_thread::sleep_for(std::chrono::milliseconds(250));
                }

                logger.info("stopping microphone capture");
                capture.stop();
                uploader.flush();
            }
        }

        logger.info("agent stopped");
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "grey-cardinal-agent error: " << exc.what() << '\n';
        return 1;
    }
}
