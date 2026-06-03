cmake_minimum_required(VERSION 3.20)

project(grey-cardinal-agent VERSION 0.1.0 LANGUAGES CXX)

include(cmake/PlatformOptions.cmake)

include(CTest)

add_library(grey-cardinal-agent-core STATIC
    src/asr_provider.cpp
    src/audio_metrics.cpp
    src/config.cpp
    src/desktop_transcript.cpp
    src/desktop_transcript_uploader.cpp
    src/logger.cpp
    src/wav_writer.cpp
    src/http_client.cpp
    src/chunk_uploader.cpp
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
            ole32
            avrt
            mmdevapi
            propsys
            uuid
    )
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
