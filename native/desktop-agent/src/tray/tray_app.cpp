// Grey Cardinal Daemon — Windows tray application.
//
// STATUS: written for the Windows target. It is NOT compiled, signed, or tray-
// tested in the Linux CI/dev container used to build this change — it must be
// built with MSVC on Windows (see CMake target `grey-cardinal-tray` and
// README_AGENT_WINDOWS.md). The account-pairing backend + ownership flow it
// drives ARE verified end-to-end (scripts/daemon_sim.py).
//
// Responsibilities:
//   - live in the system tray with status (Idle/Recording/Uploading/Error);
//   - menu: Start/Stop recording, Open Cockpit, Pair device, Settings, Logs, Quit;
//   - pair the device to a workspace via POST /api/agents/register (pairing code);
//   - heartbeat every 30s (POST /api/agents/heartbeat, X-Agent-Token);
//   - controlled session recording: Start creates a WAV, Stop uploads it to
//     POST /api/daemon/uploads with the per-device agent_token.
//
// The daemon records ONLY between an explicit Start and Stop. No always-on
// listening. The agent_token lives only in the local config — never in the MSI.

#ifdef _WIN32

#include <windows.h>
#include <shellapi.h>
#include <winhttp.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cwctype>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <sstream>
#include <string>
#include <thread>

#pragma comment(lib, "winhttp.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "user32.lib")

#include "grey_cardinal_agent/audio_capture.hpp"
#include "grey_cardinal_agent/audio_recorder.hpp"
#include "grey_cardinal_agent/config.hpp"
#include "grey_cardinal_agent/http_client.hpp"
#include "grey_cardinal_agent/logger.hpp"
#include "wasapi_loopback_capture.hpp"
#include <memory>
#include <vector>

namespace gca = grey_cardinal_agent;

namespace {

constexpr UINT WM_TRAY = WM_APP + 1;
constexpr UINT WM_REC_DONE = WM_APP + 2;  // posted from the upload worker thread
constexpr UINT ID_START = 1001;
constexpr UINT ID_STOP = 1002;
constexpr UINT ID_COCKPIT = 1003;
constexpr UINT ID_PAIR = 1004;
constexpr UINT ID_SETTINGS = 1005;
constexpr UINT ID_LOGS = 1006;
constexpr UINT ID_QUIT = 1007;
constexpr UINT TIMER_HEARTBEAT = 1;

enum class Status { Idle, Recording, Uploading, Error };

struct Config {
    std::wstring backend_url = L"https://fishingteam.su";
    std::wstring agent_id;
    std::wstring workspace_id;
    std::wstring agent_token;
    std::wstring device_name;
};

std::filesystem::path config_dir() {
    wchar_t* base = nullptr;
    size_t len = 0;
    _wdupenv_s(&base, &len, L"LOCALAPPDATA");
    std::filesystem::path p = base ? base : L".";
    free(base);
    return p / L"GreyCardinal" / L"Daemon";
}
std::filesystem::path config_path() { return config_dir() / L"config.toml"; }
std::filesystem::path log_dir() { return config_dir() / L"logs"; }

std::wstring trim_quotes(std::wstring v) {
    if (v.size() >= 2 && v.front() == L'"' && v.back() == L'"') return v.substr(1, v.size() - 2);
    return v;
}

Config load_config() {
    Config c;
    std::wifstream f(config_path());
    std::wstring line;
    while (std::getline(f, line)) {
        auto eq = line.find(L'=');
        if (eq == std::wstring::npos || line[0] == L'#') continue;
        std::wstring key = line.substr(0, eq);
        std::wstring val = trim_quotes(line.substr(eq + 1));
        key.erase(remove_if(key.begin(), key.end(), iswspace), key.end());
        // value: strip leading spaces only
        while (!val.empty() && iswspace(val.front())) val.erase(val.begin());
        if (key == L"backend_url") c.backend_url = val;
        else if (key == L"agent_id") c.agent_id = val;
        else if (key == L"workspace_id") c.workspace_id = val;
        else if (key == L"agent_token") c.agent_token = val;
        else if (key == L"device_name") c.device_name = val;
    }
    return c;
}

void save_config(const Config& c) {
    std::filesystem::create_directories(config_dir());
    std::wofstream f(config_path(), std::ios::trunc);
    f << L"# Grey Cardinal Daemon config (managed by the tray app)\n";
    f << L"backend_url = \"" << c.backend_url << L"\"\n";
    f << L"agent_id = \"" << c.agent_id << L"\"\n";
    f << L"workspace_id = \"" << c.workspace_id << L"\"\n";
    f << L"agent_token = \"" << c.agent_token << L"\"\n";
    f << L"device_name = \"" << c.device_name << L"\"\n";
}

// Minimal WinHTTP POST helper. Returns response body (UTF-8) and sets ok.
std::string http_post(const std::wstring& url, const std::string& body,
                      const std::wstring& content_type, const std::wstring& agent_token,
                      bool& ok) {
    ok = false;
    URL_COMPONENTS uc{};
    uc.dwStructSize = sizeof(uc);
    wchar_t host[256]{}, path[1024]{};
    uc.lpszHostName = host; uc.dwHostNameLength = 255;
    uc.lpszUrlPath = path; uc.dwUrlPathLength = 1023;
    if (!WinHttpCrackUrl(url.c_str(), 0, 0, &uc)) return {};
    bool https = (uc.nScheme == INTERNET_SCHEME_HTTPS);

    HINTERNET ses = WinHttpOpen(L"GreyCardinalDaemon/0.4.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!ses) return {};
    HINTERNET con = WinHttpConnect(ses, host, uc.nPort, 0);
    std::wstring headers = L"Content-Type: " + content_type + L"\r\n";
    if (!agent_token.empty()) headers += L"X-Agent-Token: " + agent_token + L"\r\n";
    HINTERNET req = con ? WinHttpOpenRequest(con, L"POST", path, nullptr, WINHTTP_NO_REFERER,
                                             WINHTTP_DEFAULT_ACCEPT_TYPES,
                                             https ? WINHTTP_FLAG_SECURE : 0)
                        : nullptr;
    // Generous receive timeout: the server transcribes the WAV (asr-service)
    // before responding. (resolve, connect, send, receive) in ms.
    if (req) WinHttpSetTimeouts(req, 0, 60000, 60000, 200000);

    // Send headers + total length, then stream the (possibly large) body via
    // WinHttpWriteData — robust for multi-hundred-KB uploads.
    const char* stage = "ok";
    DWORD err = 0;
    auto send_body = [&]() -> bool {
        if (!WinHttpSendRequest(req, headers.c_str(), (DWORD)-1L, WINHTTP_NO_REQUEST_DATA, 0,
                                (DWORD)body.size(), 0)) {
            stage = "sendrequest";
            err = GetLastError();
            return false;
        }
        const char* p = body.data();
        DWORD remaining = (DWORD)body.size();
        while (remaining > 0) {
            DWORD chunk = remaining > 65536 ? 65536 : remaining;
            DWORD written = 0;
            if (!WinHttpWriteData(req, p, chunk, &written)) {
                stage = "writedata";
                err = GetLastError();
                return false;
            }
            p += written;
            remaining -= written;
        }
        return true;
    };

    std::string out;
    bool sent = req && send_body();
    if (sent && !WinHttpReceiveResponse(req, nullptr)) {
        stage = "receive";
        err = GetLastError();
        sent = false;
    }
    if (sent) {
        DWORD code = 0, sz = sizeof(code);
        WinHttpQueryHeaders(req, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                            WINHTTP_HEADER_NAME_BY_INDEX, &code, &sz, WINHTTP_NO_HEADER_INDEX);
        DWORD avail = 0;
        while (WinHttpQueryDataAvailable(req, &avail) && avail) {
            std::string buf(avail, '\0');
            DWORD read = 0;
            WinHttpReadData(req, buf.data(), avail, &read);
            out.append(buf.data(), read);
        }
        ok = (code >= 200 && code < 300);
        if (!ok) out = "[http " + std::to_string(code) + "] " + out;
    } else {
        out = std::string("[winhttp fail stage=") + stage + " err=" + std::to_string(err) + "]";
    }
    if (req) WinHttpCloseHandle(req);
    if (con) WinHttpCloseHandle(con);
    WinHttpCloseHandle(ses);
    return out;
}

std::string narrow(const std::wstring& w) {
    if (w.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string s(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), s.data(), n, nullptr, nullptr);
    return s;
}

// Naive JSON string field extractor (sufficient for our small responses).
std::wstring json_field(const std::string& json, const std::string& key) {
    auto pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return {};
    pos = json.find(':', pos);
    pos = json.find('"', pos);
    auto end = json.find('"', pos + 1);
    std::string v = json.substr(pos + 1, end - pos - 1);
    int n = MultiByteToWideChar(CP_UTF8, 0, v.c_str(), (int)v.size(), nullptr, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, v.c_str(), (int)v.size(), w.data(), n);
    return w;
}

// Globals (single-window app).
Config g_cfg;
Status g_status = Status::Idle;
NOTIFYICONDATAW g_nid{};
std::atomic<bool> g_running{true};
std::chrono::steady_clock::time_point g_rec_start;

// Recording session (real WASAPI capture → WAV → upload).
gca::AgentConfig g_agent_cfg;
std::unique_ptr<gca::Logger> g_logger;
std::unique_ptr<gca::AudioRecorder> g_recorder;
std::unique_ptr<gca::WindowsWasapiCapture> g_capture;
std::string g_rec_id;
std::string g_rec_started_iso;

// Upload the recorded WAV to /api/daemon/uploads. The WAV is already on disk, so
// we shell out to the system curl.exe (present on Windows 10 1803+/11) for a
// robust multipart upload with the X-Agent-Token header. Runs hidden; the JSON
// response is written to a file and parsed for "ok":true.
bool upload_recording(const std::filesystem::path& wav) {
    std::error_code ec;
    if (!std::filesystem::exists(wav, ec) || std::filesystem::file_size(wav, ec) == 0) {
        return false;
    }
    wchar_t sysdir[MAX_PATH]{};
    GetSystemDirectoryW(sysdir, MAX_PATH);
    std::wstring curl = std::wstring(sysdir) + L"\\curl.exe";
    std::filesystem::path resp = config_dir() / L"last_upload.json";
    std::wstring rec_id(g_rec_id.begin(), g_rec_id.end());

    std::wstring cmd = L"\"" + curl + L"\" -s --max-time 200 -X POST \"" + g_cfg.backend_url +
                       L"/api/daemon/uploads\"" + L" -H \"X-Agent-Token: " + g_cfg.agent_token +
                       L"\"" + L" -F \"audio=@" + wav.wstring() + L";type=audio/wav\"" +
                       L" -F \"recording_id=" + rec_id + L"\"" + L" -F \"source=microphone\"" +
                       L" -o \"" + resp.wstring() + L"\"";

    STARTUPINFOW si{};
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi{};
    std::vector<wchar_t> cl(cmd.begin(), cmd.end());
    cl.push_back(L'\0');
    if (!CreateProcessW(nullptr, cl.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr,
                        nullptr, &si, &pi)) {
        if (g_logger) g_logger->error("curl spawn failed err=" + std::to_string(GetLastError()));
        return false;
    }
    WaitForSingleObject(pi.hProcess, 210000);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);

    std::ifstream rf(resp, std::ios::binary);
    std::string body((std::istreambuf_iterator<char>(rf)), std::istreambuf_iterator<char>());
    bool ok = (code == 0) && body.find("\"ok\":true") != std::string::npos;
    if (g_logger) {
        g_logger->info("curl upload exit=" + std::to_string(code) + " ok=" + (ok ? "1" : "0") +
                       " resp=" + body.substr(0, 160));
    }
    return ok;
}

const wchar_t* status_text(Status s) {
    switch (s) {
        case Status::Recording: return L"Recording";
        case Status::Uploading: return L"Uploading";
        case Status::Error: return L"Error";
        default: return L"Idle";
    }
}

void update_tray() {
    std::wstring tip = L"Grey Cardinal Daemon — ";
    tip += status_text(g_status);
    if (g_status == Status::Recording) {
        auto secs = std::chrono::duration_cast<std::chrono::seconds>(
                        std::chrono::steady_clock::now() - g_rec_start)
                        .count();
        wchar_t buf[32];
        swprintf(buf, 32, L" %02lld:%02lld", secs / 60, secs % 60);
        tip += buf;
    }
    wcsncpy_s(g_nid.szTip, tip.c_str(), _TRUNCATE);
    Shell_NotifyIconW(NIM_MODIFY, &g_nid);
}

void notify(const wchar_t* title, const wchar_t* msg) {
    g_nid.uFlags |= NIF_INFO;
    wcsncpy_s(g_nid.szInfoTitle, title, _TRUNCATE);
    wcsncpy_s(g_nid.szInfo, msg, _TRUNCATE);
    Shell_NotifyIconW(NIM_MODIFY, &g_nid);
    g_nid.uFlags &= ~NIF_INFO;
}

// POST a JSON body via the system curl.exe. The body is written to a temp file
// (no command-line quoting issues) and the response is read back. Robust on
// networks where raw WinHTTP from this app is unreliable.
std::string curl_post_json(const std::wstring& url, const std::string& json, bool with_token,
                           bool& ok) {
    ok = false;
    wchar_t sysdir[MAX_PATH]{};
    GetSystemDirectoryW(sysdir, MAX_PATH);
    std::filesystem::create_directories(config_dir());
    std::filesystem::path bodyf = config_dir() / L"req.json";
    std::filesystem::path respf = config_dir() / L"resp.json";
    {
        std::ofstream bf(bodyf, std::ios::binary);
        bf.write(json.data(), (std::streamsize)json.size());
    }
    std::wstring cmd = L"\"" + std::wstring(sysdir) + L"\\curl.exe\" -s --max-time 60 -X POST \"" +
                       url + L"\" -H \"Content-Type: application/json\"";
    if (with_token) cmd += L" -H \"X-Agent-Token: " + g_cfg.agent_token + L"\"";
    cmd += L" --data-binary @\"" + bodyf.wstring() + L"\" -o \"" + respf.wstring() + L"\"";

    STARTUPINFOW si{};
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi{};
    std::vector<wchar_t> cl(cmd.begin(), cmd.end());
    cl.push_back(L'\0');
    if (!CreateProcessW(nullptr, cl.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr,
                        nullptr, &si, &pi)) {
        return {};
    }
    WaitForSingleObject(pi.hProcess, 65000);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    std::ifstream rf(respf, std::ios::binary);
    std::string body((std::istreambuf_iterator<char>(rf)), std::istreambuf_iterator<char>());
    ok = (code == 0) && body.find("\"ok\":true") != std::string::npos;
    return body;
}

void send_heartbeat(const wchar_t* status) {
    if (g_cfg.agent_token.empty()) return;
    std::string body = std::string("{\"status\":\"") + narrow(status) + "\",\"version\":\"0.4.0\"}";
    bool ok = false;
    curl_post_json(g_cfg.backend_url + L"/api/agents/heartbeat", body, true, ok);
}

// --- Pairing dialog (minimal): prompt for a code, POST /api/agents/register ---
INT_PTR CALLBACK pair_proc(HWND dlg, UINT msg, WPARAM wp, LPARAM) {
    if (msg == WM_COMMAND && LOWORD(wp) == IDOK) {
        wchar_t code[64]{};
        GetDlgItemTextW(dlg, 100, code, 64);
        wchar_t name[128]{};
        DWORD n = 128;
        GetComputerNameW(name, &n);
        std::string body = std::string("{\"pairing_code\":\"") + narrow(code) +
                           "\",\"device_name\":\"" + narrow(name) +
                           "\",\"os\":\"windows\",\"daemon_version\":\"0.4.0\"}";
        bool ok = false;
        std::string resp =
            curl_post_json(g_cfg.backend_url + L"/api/agents/register", body, false, ok);
        if (ok) {
            g_cfg.agent_token = json_field(resp, "agent_token");
            g_cfg.agent_id = json_field(resp, "agent_id");
            g_cfg.workspace_id = json_field(resp, "workspace_id");
            std::wstring be = json_field(resp, "backend_url");
            if (!be.empty()) g_cfg.backend_url = be;
            g_cfg.device_name = name;
            save_config(g_cfg);
            notify(L"Grey Cardinal", L"Device paired to workspace");
        } else {
            MessageBoxW(dlg, L"Pairing failed — check the code and try again.", L"Grey Cardinal",
                        MB_ICONERROR);
        }
        EndDialog(dlg, IDOK);
        return TRUE;
    }
    if (msg == WM_COMMAND && LOWORD(wp) == IDCANCEL) {
        EndDialog(dlg, IDCANCEL);
        return TRUE;
    }
    return FALSE;
}

void do_pair(HWND owner) {
    // Pairing dialog (id 200) lives in tray.rc; pair_proc handles register.
    DialogBoxParamW(GetModuleHandleW(nullptr), MAKEINTRESOURCEW(200), owner, pair_proc, 0);
}

void start_recording() {
    if (g_cfg.agent_token.empty()) {
        notify(L"Grey Cardinal", L"Pair the device first (tray → Pair device).");
        return;
    }
    try {
        g_agent_cfg = gca::AgentConfig{};
        g_agent_cfg.output_dir = config_dir();
        g_agent_cfg.capture_mode = gca::CaptureMode::Microphone;
        g_rec_id = gca::generate_uuid();
        g_rec_started_iso = gca::format_iso8601(std::chrono::system_clock::now());

        std::filesystem::create_directories(log_dir());
        g_logger = std::make_unique<gca::Logger>(log_dir() / L"daemon.log");
        g_recorder = std::make_unique<gca::AudioRecorder>(g_agent_cfg, *g_logger);
        g_recorder->start();
        g_capture = std::make_unique<gca::WindowsWasapiCapture>(
            gca::WindowsWasapiEndpointKind::InputMicrophone);
        g_capture->start([](const gca::AudioFrame& frame) {
            if (g_recorder) g_recorder->handle_frame(frame);
        });
    } catch (const std::exception&) {
        g_capture.reset();
        g_recorder.reset();
        g_logger.reset();
        g_status = Status::Error;
        update_tray();
        notify(L"Grey Cardinal", L"Could not start microphone capture — open logs");
        return;
    }
    g_status = Status::Recording;
    g_rec_start = std::chrono::steady_clock::now();
    update_tray();
    send_heartbeat(L"recording");
}

void stop_recording(HWND hwnd) {
    if (!g_capture && !g_recorder) return;
    g_status = Status::Uploading;
    update_tray();
    // Finalize + upload off the UI thread so the menu stays responsive.
    std::thread([hwnd]() {
        bool ok = false;
        try {
            if (g_capture) g_capture->stop();
            if (g_recorder) g_recorder->stop();
            std::filesystem::path wav =
                g_recorder ? g_recorder->outputFilePath() : std::filesystem::path{};
            if (!wav.empty() && g_recorder && g_recorder->hasData()) {
                ok = upload_recording(wav);
            }
        } catch (const std::exception&) {
            ok = false;
        }
        g_capture.reset();
        g_recorder.reset();
        g_logger.reset();
        send_heartbeat(ok ? L"idle" : L"error");
        PostMessageW(hwnd, WM_REC_DONE, ok ? 1 : 0, 0);
    }).detach();
}

void show_menu(HWND hwnd) {
    POINT pt;
    GetCursorPos(&pt);
    HMENU m = CreatePopupMenu();
    bool rec = (g_status == Status::Recording);
    AppendMenuW(m, MF_STRING | (rec ? MF_GRAYED : 0), ID_START, L"Начать запись");
    AppendMenuW(m, MF_STRING | (rec ? 0 : MF_GRAYED), ID_STOP, L"Остановить запись");
    AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m, MF_STRING, ID_COCKPIT, L"Open Cockpit");
    AppendMenuW(m, MF_STRING, ID_PAIR, L"Pair device");
    AppendMenuW(m, MF_STRING, ID_SETTINGS, L"Settings");
    AppendMenuW(m, MF_STRING, ID_LOGS, L"Open Logs");
    AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m, MF_STRING, ID_QUIT, L"Quit");
    SetForegroundWindow(hwnd);
    TrackPopupMenu(m, TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, nullptr);
    DestroyMenu(m);
}

LRESULT CALLBACK wnd_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_TRAY:
            if (LOWORD(lp) == WM_RBUTTONUP || LOWORD(lp) == WM_LBUTTONUP) show_menu(hwnd);
            return 0;
        case WM_REC_DONE: {
            bool ok = (wp != 0);
            g_status = ok ? Status::Idle : Status::Error;
            update_tray();
            notify(L"Grey Cardinal", ok ? L"Recording uploaded to Grey Cardinal"
                                        : L"Upload failed — open logs");
            return 0;
        }
        case WM_TIMER:
            if (wp == TIMER_HEARTBEAT) {
                send_heartbeat(g_status == Status::Recording ? L"recording" : L"idle");
                update_tray();
            }
            return 0;
        case WM_COMMAND:
            switch (LOWORD(wp)) {
                case ID_START: start_recording(); break;
                case ID_STOP: stop_recording(hwnd); break;
                case ID_COCKPIT:
                    ShellExecuteW(nullptr, L"open", g_cfg.backend_url.c_str(), nullptr, nullptr,
                                  SW_SHOW);
                    break;
                case ID_PAIR: do_pair(hwnd); break;
                case ID_SETTINGS:
                    ShellExecuteW(nullptr, L"open", config_path().c_str(), nullptr, nullptr,
                                  SW_SHOW);
                    break;
                case ID_LOGS:
                    std::filesystem::create_directories(log_dir());
                    ShellExecuteW(nullptr, L"open", log_dir().c_str(), nullptr, nullptr, SW_SHOW);
                    break;
                case ID_QUIT:
                    g_running = false;
                    DestroyWindow(hwnd);
                    break;
            }
            return 0;
        case WM_DESTROY:
            Shell_NotifyIconW(NIM_DELETE, &g_nid);
            PostQuitMessage(0);
            return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

}  // namespace

// Headless self-test: record from the mic for `seconds`, upload to the backend,
// log the result, and exit. Used for diagnostics / CI (no tray interaction).
int run_record_test(int seconds) {
    g_cfg = load_config();
    std::filesystem::create_directories(log_dir());
    g_logger = std::make_unique<gca::Logger>(log_dir() / L"daemon.log");
    if (g_cfg.agent_token.empty()) {
        g_logger->error("record-test: not paired (no agent_token)");
        return 2;
    }
    try {
        g_agent_cfg = gca::AgentConfig{};
        g_agent_cfg.output_dir = config_dir();
        g_agent_cfg.capture_mode = gca::CaptureMode::Microphone;
        g_rec_id = gca::generate_uuid();
        g_rec_started_iso = gca::format_iso8601(std::chrono::system_clock::now());
        g_recorder = std::make_unique<gca::AudioRecorder>(g_agent_cfg, *g_logger);
        g_recorder->start();
        g_capture = std::make_unique<gca::WindowsWasapiCapture>(
            gca::WindowsWasapiEndpointKind::InputMicrophone);
        g_capture->start([](const gca::AudioFrame& frame) {
            if (g_recorder) g_recorder->handle_frame(frame);
        });
        Sleep((DWORD)seconds * 1000);
        g_capture->stop();
        g_recorder->stop();
        std::filesystem::path wav = g_recorder->outputFilePath();
        bool ok = !wav.empty() && g_recorder->hasData() && upload_recording(wav);
        g_logger->info(std::string("record-test upload ok=") + (ok ? "1" : "0"));
        return ok ? 0 : 1;
    } catch (const std::exception& e) {
        g_logger->error(std::string("record-test failed: ") + e.what());
        return 3;
    }
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE, LPWSTR, int) {
    if (std::wstring(GetCommandLineW()).find(L"--record-test") != std::wstring::npos) {
        return run_record_test(6);
    }
    g_cfg = load_config();

    WNDCLASSW wc{};
    wc.lpfnWndProc = wnd_proc;
    wc.hInstance = inst;
    wc.lpszClassName = L"GreyCardinalTray";
    RegisterClassW(&wc);
    HWND hwnd = CreateWindowW(wc.lpszClassName, L"Grey Cardinal Daemon", 0, 0, 0, 0, 0,
                              HWND_MESSAGE, nullptr, inst, nullptr);

    g_nid.cbSize = sizeof(g_nid);
    g_nid.hWnd = hwnd;
    g_nid.uID = 1;
    g_nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    g_nid.uCallbackMessage = WM_TRAY;
    g_nid.hIcon = LoadIconW(inst, MAKEINTRESOURCEW(101));  // app icon from .rc
    if (!g_nid.hIcon) g_nid.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
    wcsncpy_s(g_nid.szTip, L"Grey Cardinal Daemon — Idle", _TRUNCATE);
    Shell_NotifyIconW(NIM_ADD, &g_nid);

    SetTimer(hwnd, TIMER_HEARTBEAT, 30000, nullptr);
    send_heartbeat(L"idle");

    MSG m;
    while (GetMessageW(&m, nullptr, 0, 0)) {
        TranslateMessage(&m);
        DispatchMessageW(&m);
    }
    return 0;
}

#endif  // _WIN32
