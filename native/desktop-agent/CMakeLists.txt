cmake_minimum_required(VERSION 3.20)

project(grey-cardinal-agent VERSION 0.4.0 LANGUAGES CXX)

include(cmake/PlatformOptions.cmake)

include(CTest)

# Core library: config, recording, upload, WAV writing, logging.
# No ASR, no task extraction, no transcript processing.
add_library(grey-cardinal-agent-core STATIC
    src/config.cpp
    src/audio_recorder.cpp
    src/uploader.cpp
    src/logger.cpp
    src/wav_writer.cpp
)

target_include_directories(grey-cardinal-agent-core
    PUBLIC
        include
)

target_compile_features(grey-cardinal-agent-core PUBLIC cxx_std_20)

if(WIN32)
    target_compile_definitions(grey-cardinal-agent-core
        PUBLIC
            _CRT_SECURE_NO_WARNINGS
            NOMINMAX
            WIN32_LEAN_AND_MEAN
            UNICODE
            _UNICODE
    )
    target_link_libraries(grey-cardinal-agent-core
        PUBLIC
            winhttp
            ole32      # CoCreateGuid for UUID generation
    )

    add_executable(grey-cardinal-agent
        src/main.cpp
    )
    target_sources(grey-cardinal-agent
        PRIVATE
            platform/windows/wasapi_loopback_capture.cpp
    )
    target_include_directories(grey-cardinal-agent
        PRIVATE
            platform/windows
    )
    target_compile_definitions(grey-cardinal-agent
        PRIVATE
            _CRT_SECURE_NO_WARNINGS
            NOMINMAX
            WIN32_LEAN_AND_MEAN
            UNICODE
            _UNICODE
            GREY_CARDINAL_WINDOWS_CAPTURE_ENABLED=1
    )
    target_link_libraries(grey-cardinal-agent
        PRIVATE
            grey-cardinal-agent-core
            avrt
            mmdevapi
            propsys
            uuid
    )

    # System-tray application (pairing, status, Start/Stop, heartbeat).
    add_executable(grey-cardinal-tray WIN32
        src/tray/tray_app.cpp
        src/tray/tray.rc
    )
    target_compile_features(grey-cardinal-tray PRIVATE cxx_std_20)
    target_compile_definitions(grey-cardinal-tray
        PRIVATE
            _CRT_SECURE_NO_WARNINGS
            NOMINMAX
            WIN32_LEAN_AND_MEAN
            UNICODE
            _UNICODE
    )
    target_link_libraries(grey-cardinal-tray
        PRIVATE
            winhttp
            shell32
            user32
            comctl32
            ole32
    )
    install(TARGETS grey-cardinal-tray RUNTIME DESTINATION .)
elseif(APPLE)
    message(FATAL_ERROR "Grey Cardinal desktop agent macOS capture is not implemented yet. See platform/macos/README.md for the adapter plan.")
elseif(UNIX)
    message(FATAL_ERROR "Grey Cardinal desktop agent Linux capture is not implemented yet. See platform/linux/README.md for the adapter plan.")
else()
    message(FATAL_ERROR "Unsupported platform for Grey Cardinal desktop agent.")
endif()

if(BUILD_TESTING)
    add_executable(grey-cardinal-agent-tests
        tests/core_tests.cpp
    )
    target_link_libraries(grey-cardinal-agent-tests
        PRIVATE
            grey-cardinal-agent-core
    )
    add_test(NAME grey-cardinal-agent-core COMMAND grey-cardinal-agent-tests)
endif()

install(TARGETS grey-cardinal-agent RUNTIME DESTINATION .)
install(FILES config.example.toml DESTINATION .)
