#include "grey_cardinal_agent/audio_recorder.hpp"
#include "grey_cardinal_agent/config.hpp"
#include "grey_cardinal_agent/logger.hpp"
#include "grey_cardinal_agent/uploader.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
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

void print_status(const std::string& status) {
    std::cout << "[" << status << "]\n" << std::flush;
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
        logger.info("Grey Cardinal desktop audio agent starting");
        logger.info("log_file=" + logger.path().string());
        logger.info("config " + config_summary(config));

        // Auto-generate meeting_id if not provided.
        if (config.meeting_id.empty()) {
            config.meeting_id = generate_uuid();
            logger.info("meeting_id auto-generated: " + config.meeting_id);
        }

#if defined(_WIN32)
        const WindowsWasapiEndpointKind endpoint_kind =
            config.capture_mode == CaptureMode::SystemLoopback
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
                std::cout << marker << "[" << device.index << "] " << device.name << "\n"
                          << "    id: " << device.id << "\n";
            }
            return 0;
        }

        // Log selected device.
        for (const auto& device : devices) {
            if (device.is_default_communications || device.is_default) {
                logger.info("capture device: " + device.name + " id=" + device.id);
                break;
            }
        }
        if (!config.input_device_id.empty()) {
            logger.info("capture device override id=" + config.input_device_id);
        } else if (config.input_device_index >= 0) {
            logger.info("capture device override index=" + std::to_string(config.input_device_index));
        }
#else
        if (config.list_devices) {
            std::cerr << "device listing is not implemented for this platform\n";
            return 2;
        }
        std::cerr << "audio capture is not implemented for this platform\n";
        return 2;
#endif

        std::signal(SIGINT, handle_signal);
        std::signal(SIGTERM, handle_signal);

        // ── IDLE → RECORDING ─────────────────────────────────────────────────

        AudioRecorder recorder(config, logger);
        recorder.start();

        print_status("recording");
        logger.info(
            "recording started"
            " meeting_id=" + config.meeting_id +
            " mode=" + capture_mode_value(config.capture_mode) +
            (config.duration_sec > 0
                ? " duration_sec=" + std::to_string(config.duration_sec)
                : " (Ctrl+C to stop)")
        );

#if defined(_WIN32)
        capture.start([&recorder](const AudioFrame& frame) {
            recorder.handle_frame(frame);
        });
#endif

        const auto rec_started = std::chrono::steady_clock::now();
        while (!g_stop_requested) {
            if (config.duration_sec > 0) {
                const auto elapsed = std::chrono::steady_clock::now() - rec_started;
                if (elapsed >= std::chrono::seconds(config.duration_sec)) {
                    logger.info("duration reached; stopping");
                    break;
                }
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
        }

        // ── RECORDING → SAVING ────────────────────────────────────────────────

        logger.info("stopping capture");
#if defined(_WIN32)
        capture.stop();
#endif
        recorder.stop();

        const auto wav_path = recorder.outputFilePath();
        if (wav_path.empty()) {
            logger.error("no audio data captured; nothing to upload");
            print_status("error: no audio captured");
            return 1;
        }

        logger.info("audio saved: " + wav_path.string());

        // ── SAVING → UPLOADING ────────────────────────────────────────────────

        print_status("uploading");
        logger.info("uploading to " + config.backend_url);

        const UploadMetadata metadata{
            config.agent_id,
            config.meeting_id,
            format_iso8601(recorder.startedAt()),
            format_iso8601(recorder.endedAt()),
        };

        Uploader uploader(config, logger);
        const UploadResult upload_result = uploader.uploadAudio(wav_path, metadata);

        // ── UPLOADING → UPLOADED / ERROR ──────────────────────────────────────

        if (upload_result.ok) {
            logger.info(
                "upload complete"
                " audio_id=" + upload_result.audio_id +
                " message=" + upload_result.message
            );
            print_status("uploaded: audio_id=" + upload_result.audio_id);
            return 0;
        } else {
            logger.error("upload failed: " + upload_result.error);
            std::cerr << "Upload failed: " << upload_result.error << "\n"
                      << "File preserved at: " << wav_path.string() << "\n";
            print_status("error: upload failed");
            return 1;
        }

    } catch (const std::exception& exc) {
        std::cerr << "grey-cardinal-agent error: " << exc.what() << '\n';
        return 1;
    }
}
