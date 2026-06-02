#include "grey_cardinal_agent/http_client.hpp"

#include <algorithm>
#include <sstream>
#include <stdexcept>

#if defined(_WIN32)
#include <windows.h>
#include <winhttp.h>
#endif

namespace grey_cardinal_agent {
namespace {

struct ParsedUrl {
    bool https = false;
    std::string host;
    int port = 80;
    std::string path = "/";
};

ParsedUrl parse_url(const std::string& url) {
    const auto scheme_end = url.find("://");
    if (scheme_end == std::string::npos) {
        throw std::runtime_error("server URL must include http:// or https://");
    }

    const std::string scheme = url.substr(0, scheme_end);
    std::string rest = url.substr(scheme_end + 3);
    ParsedUrl parsed;
    parsed.https = scheme == "https";
    parsed.port = parsed.https ? 443 : 80;

    if (scheme != "http" && scheme != "https") {
        throw std::runtime_error("unsupported URL scheme: " + scheme);
    }

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
        throw std::runtime_error("server URL host is empty");
    }

    return parsed;
}

std::string endpoint_path(std::string base_path) {
    if (base_path.empty()) {
        base_path = "/";
    }
    while (base_path.size() > 1 && base_path.back() == '/') {
        base_path.pop_back();
    }
    if (base_path == "/") {
        return "/audio/chunk";
    }
    return base_path + "/audio/chunk";
}

#if defined(_WIN32)
std::wstring widen_utf8(const std::string& value) {
    if (value.empty()) {
        return {};
    }

    const int needed = MultiByteToWideChar(
        CP_UTF8,
        0,
        value.data(),
        static_cast<int>(value.size()),
        nullptr,
        0
    );
    if (needed <= 0) {
        return std::wstring(value.begin(), value.end());
    }

    std::wstring output(static_cast<std::size_t>(needed), L'\0');
    MultiByteToWideChar(
        CP_UTF8,
        0,
        value.data(),
        static_cast<int>(value.size()),
        output.data(),
        needed
    );
    return output;
}

struct WinHttpHandle {
    HINTERNET handle = nullptr;

    explicit WinHttpHandle(HINTERNET value = nullptr) : handle(value) {}
    ~WinHttpHandle() {
        if (handle != nullptr) {
            WinHttpCloseHandle(handle);
        }
    }

    WinHttpHandle(const WinHttpHandle&) = delete;
    WinHttpHandle& operator=(const WinHttpHandle&) = delete;
};

std::string last_error_message() {
    const DWORD error = GetLastError();
    std::ostringstream output;
    output << "WinHTTP error " << error;
    return output.str();
}
#endif

} // namespace

AudioChunkRequestPreview build_audio_chunk_request_preview(const AudioChunkUpload& upload) {
    ParsedUrl parsed = parse_url(upload.server_url);

    AudioChunkRequestPreview preview;
    preview.endpoint_path = endpoint_path(parsed.path);
    preview.headers = {
        {"Content-Type", "audio/wav"},
        {"X-Internal-Token", upload.internal_token},
        {"X-Meeting-Id", upload.meeting_id},
        {"X-Chunk-Seq", std::to_string(upload.chunk_seq)},
        {"X-Audio-Format", "wav"},
        {"X-Audio-Sample-Rate", std::to_string(upload.format.sample_rate)},
        {"X-Audio-Channels", std::to_string(upload.format.channels)},
        {"X-Audio-Bits-Per-Sample", std::to_string(upload.format.bits_per_sample)},
    };
    return preview;
}

HttpUploadResult HttpClient::post_audio_chunk(const AudioChunkUpload& upload) const {
#if defined(_WIN32)
    HttpUploadResult result;

    ParsedUrl parsed;
    try {
        parsed = parse_url(upload.server_url);
    } catch (const std::exception& exc) {
        result.error = exc.what();
        return result;
    }

    const std::wstring host = widen_utf8(parsed.host);
    const AudioChunkRequestPreview request_preview = build_audio_chunk_request_preview(upload);
    const std::wstring path = widen_utf8(request_preview.endpoint_path);

    WinHttpHandle session(WinHttpOpen(
        L"GreyCardinalAgent/0.1",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0
    ));
    if (session.handle == nullptr) {
        result.error = last_error_message();
        return result;
    }

    WinHttpHandle connection(WinHttpConnect(
        session.handle,
        host.c_str(),
        static_cast<INTERNET_PORT>(parsed.port),
        0
    ));
    if (connection.handle == nullptr) {
        result.error = last_error_message();
        return result;
    }

    const DWORD flags = parsed.https ? WINHTTP_FLAG_SECURE : 0;
    WinHttpHandle request(WinHttpOpenRequest(
        connection.handle,
        L"POST",
        path.c_str(),
        nullptr,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        flags
    ));
    if (request.handle == nullptr) {
        result.error = last_error_message();
        return result;
    }

    std::ostringstream headers_ascii;
    for (const auto& [name, value] : request_preview.headers) {
        headers_ascii << name << ": " << value << "\r\n";
    }

    const std::wstring headers = widen_utf8(headers_ascii.str());
    const auto body_size = static_cast<DWORD>(upload.wav_bytes.size());
    auto* body = reinterpret_cast<void*>(const_cast<std::byte*>(upload.wav_bytes.data()));

    if (!WinHttpSendRequest(
            request.handle,
            headers.c_str(),
            static_cast<DWORD>(headers.size()),
            body,
            body_size,
            body_size,
            0
        )) {
        result.error = last_error_message();
        return result;
    }

    if (!WinHttpReceiveResponse(request.handle, nullptr)) {
        result.error = last_error_message();
        return result;
    }

    DWORD status_code = 0;
    DWORD status_size = sizeof(status_code);
    if (WinHttpQueryHeaders(
            request.handle,
            WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
            WINHTTP_HEADER_NAME_BY_INDEX,
            &status_code,
            &status_size,
            WINHTTP_NO_HEADER_INDEX
        )) {
        result.status_code = static_cast<int>(status_code);
    }

    std::string response_body;
    DWORD available = 0;
    while (WinHttpQueryDataAvailable(request.handle, &available) && available > 0) {
        std::string chunk(available, '\0');
        DWORD read = 0;
        if (!WinHttpReadData(request.handle, chunk.data(), available, &read)) {
            result.error = last_error_message();
            return result;
        }
        chunk.resize(read);
        response_body += chunk;
    }

    result.body = response_body;
    result.ok = result.status_code >= 200 && result.status_code < 300;
    if (!result.ok && result.error.empty()) {
        std::ostringstream output;
        output << "HTTP status " << result.status_code;
        result.error = output.str();
    }

    return result;
#else
    (void)upload;
    return {
        false,
        0,
        {},
        "HTTP upload is not implemented for this platform yet"
    };
#endif
}

} // namespace grey_cardinal_agent
