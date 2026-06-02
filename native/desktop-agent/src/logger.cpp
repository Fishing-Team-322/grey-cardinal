#include "grey_cardinal_agent/logger.hpp"

#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <sstream>

namespace grey_cardinal_agent {
namespace {

std::string timestamp_now() {
    const auto now = std::chrono::system_clock::now();
    const auto time = std::chrono::system_clock::to_time_t(now);
    std::tm local_time{};

#if defined(_WIN32)
    localtime_s(&local_time, &time);
#else
    localtime_r(&time, &local_time);
#endif

    std::ostringstream output;
    output << std::put_time(&local_time, "%Y-%m-%d %H:%M:%S");
    return output.str();
}

std::filesystem::path env_path(const char* name) {
    if (const char* value = std::getenv(name)) {
        return value;
    }
    return {};
}

} // namespace

Logger::Logger(std::filesystem::path log_path)
    : log_path_(std::move(log_path)) {
    std::filesystem::create_directories(log_path_.parent_path());
    file_.open(log_path_, std::ios::app);
}

Logger::~Logger() = default;

std::filesystem::path Logger::default_log_path() {
    if (const auto local_app_data = env_path("LOCALAPPDATA"); !local_app_data.empty()) {
        return local_app_data / "GreyCardinal" / "Agent" / "logs" / "agent.log";
    }
    if (const auto home = env_path("HOME"); !home.empty()) {
        return home / ".local" / "state" / "grey-cardinal-agent" / "logs" / "agent.log";
    }
    return std::filesystem::current_path() / "agent.log";
}

void Logger::info(const std::string& message) {
    write("INFO", message);
}

void Logger::warn(const std::string& message) {
    write("WARN", message);
}

void Logger::error(const std::string& message) {
    write("ERROR", message);
}

void Logger::write(const std::string& level, const std::string& message) {
    std::lock_guard<std::mutex> lock(mutex_);
    const std::string line = timestamp_now() + " [" + level + "] " + message;

    std::cout << line << '\n';
    if (file_) {
        file_ << line << '\n';
        file_.flush();
    }
}

} // namespace grey_cardinal_agent

