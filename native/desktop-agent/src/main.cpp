#include "grey_cardinal_agent/chunk_uploader.hpp"
#include "grey_cardinal_agent/config.hpp"
#include "grey_cardinal_agent/logger.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <exception>
#include <iostream>
#include <thread>

#if defined(_WIN32)
#include "wasapi_loopback_capture.hpp"
#endif

namespace {

std::atomic_bool g_stop_requested{false};

void handle_signal(int) {
    g_stop_requested = true;
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

#if defined(_WIN32)
        WindowsWasapiLoopbackCapture capture;
#else
        std::cerr << "desktop agent capture is not implemented for this platform yet\n";
        return 2;
#endif

        const auto devices = capture.list_devices();
        if (config.list_devices) {
            for (const auto& device : devices) {
                std::cout << (device.is_default ? "* " : "  ")
                          << device.name << " [" << device.id << "]\n";
            }
            return 0;
        }

        for (const auto& device : devices) {
            if (device.is_default) {
                logger.info("selected audio device " + device.name);
                break;
            }
        }

        if (config.internal_token.empty() && !config.dry_run) {
            logger.warn("internal token is empty; uploads will likely be rejected");
        }

        std::signal(SIGINT, handle_signal);
        std::signal(SIGTERM, handle_signal);

        ChunkUploader uploader(config, logger);
        capture.start([&uploader](const AudioFrame& frame) {
            uploader.handle_frame(frame);
        });

        logger.info("capture started; press Ctrl+C to stop");
        const auto started_at = std::chrono::steady_clock::now();
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

        logger.info("stopping capture");
        capture.stop();
        uploader.flush();
        logger.info("agent stopped");
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "grey-cardinal-agent error: " << exc.what() << '\n';
        return 1;
    }
}
