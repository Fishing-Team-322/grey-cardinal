#pragma once

#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>

namespace grey_cardinal_agent {

class Logger {
public:
    explicit Logger(std::filesystem::path log_path);
    ~Logger();

    Logger(const Logger&) = delete;
    Logger& operator=(const Logger&) = delete;

    static std::filesystem::path default_log_path();

    void info(const std::string& message);
    void warn(const std::string& message);
    void error(const std::string& message);

    const std::filesystem::path& path() const { return log_path_; }

private:
    void write(const std::string& level, const std::string& message);

    std::filesystem::path log_path_;
    std::ofstream file_;
    std::mutex mutex_;
};

} // namespace grey_cardinal_agent

