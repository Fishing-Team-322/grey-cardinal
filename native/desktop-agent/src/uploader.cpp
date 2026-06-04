#include "grey_cardinal_agent/uploader.hpp"

#include <algorithm>
#include <fstream>
#include <sstream>
#include <stdexcept>

#if defined(_WIN32)
#include <windows.h>
#include <winhttp.h>
#endif

namespace grey_cardinal_agent {
namespace {

// ── URL parser ────────────────────────────────────────────────────────────────

struct ParsedUrl {
    bool https = false;
    std::string host;
    int port = 80;
    std::string path = "/";
};

ParsedUrl parse_url(const std::string& url) {
    const auto scheme_end = url.find("://");
    if (scheme_end == std::string::npos) {
        throw std::runtime_error("backend URL must include http:// or https://");
    }
    const std::string scheme = url.substr(0, scheme_end);
    std::string rest = url.substr(scheme_end + 3);
    if (scheme != "http" && scheme != "https") {
        throw std::runtime_error("unsupported URL scheme: " + scheme);
    }

    ParsedUrl parsed;
    parsed.https = (scheme == "https");
    parsed.port = parsed.https ? 443 : 80;

    const auto path_start = rest.find('/');
    std::string host_port;
    if (path_start == std::string::npos) {
        host_port = rest;
        parsed.path = "/";
    } else {
        host_port = rest.substr(0, path_start);
        parsed.path = rest.substr(path_start);
    }

    const auto port_start = host_port.rfind(':');
    if (port_start != std::string::npos && host_port.find(']') == std::string::npos) {
        parsed.host = host_port.substr(0, port_start);
        parsed.port = std::stoi(host_port.substr(port_start + 1));
    } else {
        parsed.host = host_port;
    }

    if (parsed.host.empty()) {
        throw std::runtime_error("backend URL host is empty");
    }

    // Build upload endpoint path
    while (parsed.path.size() > 1 && parsed.path.back() == '/') {
        parsed.path.pop_back();
    }
    if (parsed.path == "/") {
        parsed.path = "/api/audio/upload";
    } else {
        parsed.path += "/api/audio/upload";
    }

    return parsed;
}

// ── Multipart form-data builder ───────────────────────────────────────────────

static const std::string kBoundary = "----GCAgentBoundary7f8a9b2c1d3e4f";

void append_str(std::vector<std::byte>& body, const std::string& s) {
    for (const char c : s) {
        body.push_back(static_cast<std::byte>(c));
    }
}

void add_field(std::vector<std::byte>& body, const std::string& name, const std::string& value) {
    append_str(body, "--" + kBoundary + "\r\n");
    append_str(body, "Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n");
    append_str(body, value + "\r\n");
}

void add_file(
    std::vector<std::byte>& body,
    const std::string& field_name,
    const std::string& filename,
    const std::vector<std::byte>& data
) {
    append_str(body, "--" + kBoundary + "\r\n");
    append_str(body,
        "Content-Disposition: form-data; name=\"" + field_name +
        "\"; filename=\"" + filename + "\"\r\n");
    append_str(body, "Content-Type: audio/wav\r\n\r\n");
    body.insert(body.end(), data.begin(), data.end());
    append_str(body, "\r\n");
}

// ── Minimal JSON field extractor ──────────────────────────────────────────────

std::string json_string_field(const std::string& json, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) { return {}; }
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) { return {}; }
    ++pos;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) { ++pos; }
    if (pos >= json.size() || json[pos] != '"') { return {}; }
    ++pos;
    std::string result;
    for (; pos < json.size(); ++pos) {
        if (json[pos] == '\\' && pos + 1 < json.size()) {
            ++pos; result.push_back(json[pos]);
        } else if (json[pos] == '"') {
            break;
        } else {
            result.push_back(json[pos]);
        }
    }
    return result;
}

bool json_bool_field(const std::string& json, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) { return false; }
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) { return false; }
    ++pos;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) { ++pos; }
    return json.substr(pos, 4) == "true";
}

// ── WinHTTP POST ──────────────────────────────────────────────────────────────

struct HttpResult {
    bool ok = false;
    int status_code = 0;
    std::string body;
    std::string error;
};

#if defined(_WIN32)

std::wstring widen(const std::string& s) {
    if (s.empty()) { return {}; }
    const int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0);
    if (n <= 0) { return std::wstring(s.begin(), s.end()); }
    std::wstring out(static_cast<std::size_t>(n), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), out.data(), n);
    return out;
}

struct WinHandle {
    HINTERNET h = nullptr;
    explicit WinHandle(HINTERNET v = nullptr) : h(v) {}
    ~WinHandle() { if (h) WinHttpCloseHandle(h); }
    WinHandle(const WinHandle&) = delete;
    WinHandle& operator=(const WinHandle&) = delete;
};

HttpResult winhttp_post_multipart(
    const ParsedUrl& parsed,
    const std::vector<std::byte>& body
) {
    HttpResult result;

    WinHandle session(WinHttpOpen(
        L"GreyCardinalAgent/0.2",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0
    ));
    if (!session.h) {
        result.error = "WinHttpOpen failed: " + std::to_string(GetLastError());
        return result;
    }

    WinHandle conn(WinHttpConnect(
        session.h,
        widen(parsed.host).c_str(),
        static_cast<INTERNET_PORT>(parsed.port),
        0
    ));
    if (!conn.h) {
        result.error = "WinHttpConnect failed: " + std::to_string(GetLastError());
        return result;
    }

    const DWORD flags = parsed.https ? WINHTTP_FLAG_SECURE : 0;
    WinHandle req(WinHttpOpenRequest(
        conn.h,
        L"POST",
        widen(parsed.path).c_str(),
        nullptr,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        flags
    ));
    if (!req.h) {
        result.error = "WinHttpOpenRequest failed: " + std::to_string(GetLastError());
        return result;
    }

    const std::string ct = "Content-Type: multipart/form-data; boundary=" + kBoundary + "\r\n";
    const std::wstring wide_ct = widen(ct);
    const auto body_size = static_cast<DWORD>(body.size());
    void* body_ptr = const_cast<void*>(static_cast<const void*>(body.data()));

    if (!WinHttpSendRequest(
            req.h,
            wide_ct.c_str(),
            static_cast<DWORD>(wide_ct.size()),
            body_ptr,
            body_size,
            body_size,
            0
        )) {
        result.error = "WinHttpSendRequest failed: " + std::to_string(GetLastError());
        return result;
    }

    if (!WinHttpReceiveResponse(req.h, nullptr)) {
        result.error = "WinHttpReceiveResponse failed: " + std::to_string(GetLastError());
        return result;
    }

    DWORD status = 0;
    DWORD status_sz = sizeof(status);
    WinHttpQueryHeaders(
        req.h,
        WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
        WINHTTP_HEADER_NAME_BY_INDEX,
        &status, &status_sz,
        WINHTTP_NO_HEADER_INDEX
    );
    result.status_code = static_cast<int>(status);

    DWORD avail = 0;
    while (WinHttpQueryDataAvailable(req.h, &avail) && avail > 0) {
        std::string chunk(avail, '\0');
        DWORD read = 0;
        if (!WinHttpReadData(req.h, chunk.data(), avail, &read)) {
            result.error = "WinHttpReadData failed: " + std::to_string(GetLastError());
            return result;
        }
        chunk.resize(read);
        result.body += chunk;
    }

    result.ok = (result.status_code >= 200 && result.status_code < 300);
    if (!result.ok && result.error.empty()) {
        result.error = "HTTP " + std::to_string(result.status_code);
    }
    return result;
}

#endif // _WIN32

} // namespace

// ── Uploader ──────────────────────────────────────────────────────────────────

Uploader::Uploader(const AgentConfig& config, Logger& logger)
    : config_(config), logger_(logger) {}

UploadResult Uploader::uploadAudio(
    const std::filesystem::path& file_path,
    const UploadMetadata& metadata
) {
    UploadResult result;

    // Read audio file into memory.
    std::ifstream in(file_path, std::ios::binary);
    if (!in) {
        result.error = "cannot open audio file: " + file_path.string();
        logger_.error("uploader: " + result.error);
        return result;
    }
    // Read the whole file by size. NOTE: do not construct vector<std::byte>
    // directly from istreambuf_iterator<char> — under C++20 MSVC that routes
    // through std::construct_at and fails to build std::byte from char (C2672).
    in.seekg(0, std::ios::end);
    const std::streamoff audio_size = in.tellg();
    in.seekg(0, std::ios::beg);
    std::vector<std::byte> audio(audio_size > 0 ? static_cast<std::size_t>(audio_size) : 0);
    if (audio_size > 0) {
        in.read(reinterpret_cast<char*>(audio.data()), audio_size);
    }
    in.close();

    logger_.info(
        "uploader: uploading"
        " file=" + file_path.string() +
        " size_bytes=" + std::to_string(audio.size()) +
        " agent_id=" + metadata.agent_id +
        " meeting_id=" + metadata.meeting_id +
        " started_at=" + metadata.started_at +
        " ended_at=" + metadata.ended_at
    );

    if (config_.dry_run) {
        logger_.info("uploader: dry-run — skipping upload, file preserved at " + file_path.string());
        result.ok = true;
        result.message = "dry-run: upload skipped";
        return result;
    }

    // Build multipart/form-data body.
    std::vector<std::byte> body;
    add_field(body, "agent_id",   metadata.agent_id);
    add_field(body, "meeting_id", metadata.meeting_id);
    add_field(body, "source",     "desktop_agent");
    add_field(body, "started_at", metadata.started_at);
    add_field(body, "ended_at",   metadata.ended_at);
    add_file(body, "audio", file_path.filename().string(), audio);
    append_str(body, "--" + kBoundary + "--\r\n");

    // Parse URL and POST.
    ParsedUrl parsed;
    try {
        parsed = parse_url(config_.backend_url);
    } catch (const std::exception& exc) {
        result.error = std::string("bad backend URL: ") + exc.what();
        logger_.error("uploader: " + result.error);
        return result;
    }

    logger_.info("uploader: POST " + config_.backend_url + "/api/audio/upload");

#if defined(_WIN32)
    for (int attempt = 1; attempt <= 3; ++attempt) {
        const HttpResult http = winhttp_post_multipart(parsed, body);
        if (http.ok) {
            logger_.info(
                "uploader: upload OK"
                " status=" + std::to_string(http.status_code) +
                " body=" + http.body
            );
            result.ok = true;
            result.audio_id = json_string_field(http.body, "audio_id");
            result.message  = json_string_field(http.body, "message");
            if (result.message.empty()) {
                result.message = "Audio uploaded successfully";
            }
            return result;
        }

        logger_.warn(
            "uploader: attempt " + std::to_string(attempt) + " failed"
            " status=" + std::to_string(http.status_code) +
            " error=" + http.error +
            " body=" + http.body
        );

        if (attempt < 3) {
            // Simple back-off: 500ms, 1000ms
            Sleep(static_cast<DWORD>(500 * attempt));
        }
    }

    result.error = "upload failed after 3 attempts; file preserved at " + file_path.string();
    logger_.error("uploader: " + result.error);
#else
    result.error = "HTTP upload not implemented for this platform";
    logger_.error("uploader: " + result.error);
#endif

    return result;
}

} // namespace grey_cardinal_agent
