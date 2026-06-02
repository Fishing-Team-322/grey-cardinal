cmake_minimum_required(VERSION 3.20)

project(grey-cardinal-agent VERSION 0.1.0 LANGUAGES CXX)

include(cmake/PlatformOptions.cmake)

add_executable(grey-cardinal-agent
    src/main.cpp
    src/config.cpp
    src/logger.cpp
    src/wav_writer.cpp
    src/http_client.cpp
    src/chunk_uploader.cpp
)

target_include_directories(grey-cardinal-agent
    PRIVATE
        include
)

target_compile_features(grey-cardinal-agent PRIVATE cxx_std_20)

if(WIN32)
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
    )
    target_link_libraries(grey-cardinal-agent
        PRIVATE
            ole32
            avrt
            mmdevapi
            winhttp
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

install(TARGETS grey-cardinal-agent RUNTIME DESTINATION .)
install(FILES config.example.toml DESTINATION .)
