#include "wasapi_loopback_capture.hpp"

#include <windows.h>
#include <audioclient.h>
#include <avrt.h>
#include <propkeydef.h>
#include <functiondiscoverykeys_devpkey.h>
#include <mmdeviceapi.h>
#include <mmreg.h>
#include <propidl.h>
#include <propsys.h>
#include <ksmedia.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <cstdint>
#include <exception>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace grey_cardinal_agent {
namespace {

template <typename T>
void release_if_needed(T*& pointer) {
    if (pointer != nullptr) {
        pointer->Release();
        pointer = nullptr;
    }
}

std::string utf16_to_utf8(const wchar_t* value) {
    if (value == nullptr) {
        return {};
    }

    const int needed = WideCharToMultiByte(CP_UTF8, 0, value, -1, nullptr, 0, nullptr, nullptr);
    if (needed <= 0) {
        return {};
    }

    std::string output(static_cast<std::size_t>(needed - 1), '\0');
    WideCharToMultiByte(CP_UTF8, 0, value, -1, output.data(), needed, nullptr, nullptr);
    return output;
}

std::wstring utf8_to_utf16(const std::string& value) {
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

void throw_if_failed(HRESULT hr, const char* operation) {
    if (FAILED(hr)) {
        throw std::runtime_error(std::string(operation) + " failed with HRESULT " + std::to_string(hr));
    }
}

bool initialize_com_for_thread() {
    const HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (SUCCEEDED(hr)) {
        return true;
    }
    if (hr == RPC_E_CHANGED_MODE) {
        return false;
    }
    throw_if_failed(hr, "CoInitializeEx");
    return false;
}

std::string device_name(IMMDevice* device) {
    IPropertyStore* properties = nullptr;
    PROPVARIANT friendly_name;
    PropVariantInit(&friendly_name);

    std::string name = "Unknown audio device";
    if (SUCCEEDED(device->OpenPropertyStore(STGM_READ, &properties)) &&
        SUCCEEDED(properties->GetValue(PKEY_Device_FriendlyName, &friendly_name)) &&
        friendly_name.vt == VT_LPWSTR) {
        name = utf16_to_utf8(friendly_name.pwszVal);
    }

    PropVariantClear(&friendly_name);
    release_if_needed(properties);
    return name;
}

std::string device_id(IMMDevice* device) {
    LPWSTR raw_id = nullptr;
    std::string id;
    if (SUCCEEDED(device->GetId(&raw_id))) {
        id = utf16_to_utf8(raw_id);
        CoTaskMemFree(raw_id);
    }
    return id;
}

EDataFlow data_flow_for_endpoint(WindowsWasapiEndpointKind endpoint_kind) {
    return endpoint_kind == WindowsWasapiEndpointKind::InputMicrophone ? eCapture : eRender;
}

DWORD stream_flags_for_endpoint(WindowsWasapiEndpointKind endpoint_kind) {
    return endpoint_kind == WindowsWasapiEndpointKind::RenderLoopback
        ? AUDCLNT_STREAMFLAGS_LOOPBACK
        : 0;
}

bool name_contains_icase(const std::string& haystack, const std::string& needle) {
    if (needle.empty()) { return true; }
    auto to_lower = [](const std::string& s) {
        std::string out = s;
        for (char& c : out) { c = static_cast<char>(std::tolower(static_cast<unsigned char>(c))); }
        return out;
    };
    return to_lower(haystack).find(to_lower(needle)) != std::string::npos;
}

const char* endpoint_label(WindowsWasapiEndpointKind endpoint_kind) {
    return endpoint_kind == WindowsWasapiEndpointKind::InputMicrophone
        ? "microphone"
        : "loopback";
}

bool is_pcm_subformat(const GUID& guid) {
    return IsEqualGUID(guid, KSDATAFORMAT_SUBTYPE_PCM) != 0;
}

bool is_float_subformat(const GUID& guid) {
    return IsEqualGUID(guid, KSDATAFORMAT_SUBTYPE_IEEE_FLOAT) != 0;
}

enum class SampleKind {
    Pcm16,
    Pcm24,
    Pcm32,
    Float32,
    Unsupported
};

struct SourceFormat {
    int sample_rate = 0;
    int channels = 0;
    int bits_per_sample = 0;
    int block_align = 0;
    SampleKind kind = SampleKind::Unsupported;
};

SourceFormat describe_format(const WAVEFORMATEX& format) {
    SourceFormat source;
    source.sample_rate = static_cast<int>(format.nSamplesPerSec);
    source.channels = static_cast<int>(format.nChannels);
    source.bits_per_sample = static_cast<int>(format.wBitsPerSample);
    source.block_align = static_cast<int>(format.nBlockAlign);

    bool is_float = format.wFormatTag == WAVE_FORMAT_IEEE_FLOAT;
    bool is_pcm = format.wFormatTag == WAVE_FORMAT_PCM;
    if (format.wFormatTag == WAVE_FORMAT_EXTENSIBLE) {
        const auto& extensible = reinterpret_cast<const WAVEFORMATEXTENSIBLE&>(format);
        is_float = is_float_subformat(extensible.SubFormat);
        is_pcm = is_pcm_subformat(extensible.SubFormat);
    }

    if (is_float) {
        if (format.wBitsPerSample == 32) {
            source.kind = SampleKind::Float32;
        }
    } else if (is_pcm) {
        if (format.wBitsPerSample == 16) {
            source.kind = SampleKind::Pcm16;
        } else if (format.wBitsPerSample == 24) {
            source.kind = SampleKind::Pcm24;
        } else if (format.wBitsPerSample == 32) {
            source.kind = SampleKind::Pcm32;
        }
    }

    return source;
}

float sample_at(const BYTE* data, const SourceFormat& format, UINT32 frame, int channel) {
    const auto* sample = data + (frame * format.block_align) + (channel * (format.bits_per_sample / 8));

    switch (format.kind) {
    case SampleKind::Float32: {
        float value = 0.0F;
        std::memcpy(&value, sample, sizeof(float));
        return std::clamp(value, -1.0F, 1.0F);
    }
    case SampleKind::Pcm16: {
        std::int16_t value = 0;
        std::memcpy(&value, sample, sizeof(std::int16_t));
        return static_cast<float>(value) / 32768.0F;
    }
    case SampleKind::Pcm24: {
        std::int32_t value =
            static_cast<std::int32_t>(sample[0]) |
            (static_cast<std::int32_t>(sample[1]) << 8) |
            (static_cast<std::int32_t>(sample[2]) << 16);
        if ((value & 0x00800000) != 0) {
            value |= static_cast<std::int32_t>(0xff000000);
        }
        return static_cast<float>(value) / 8388608.0F;
    }
    case SampleKind::Pcm32: {
        std::int32_t value = 0;
        std::memcpy(&value, sample, sizeof(std::int32_t));
        return static_cast<float>(value) / 2147483648.0F;
    }
    case SampleKind::Unsupported:
        break;
    }
    return 0.0F;
}

std::vector<std::byte> convert_to_mono_pcm16(
    const BYTE* data,
    UINT32 frames,
    DWORD flags,
    const SourceFormat& source
) {
    std::vector<std::byte> output;
    output.resize(static_cast<std::size_t>(frames) * sizeof(std::int16_t));

    auto* out = reinterpret_cast<std::int16_t*>(output.data());
    if ((flags & AUDCLNT_BUFFERFLAGS_SILENT) != 0 || data == nullptr) {
        std::fill(out, out + frames, static_cast<std::int16_t>(0));
        return output;
    }

    for (UINT32 frame = 0; frame < frames; ++frame) {
        float mixed = 0.0F;
        for (int channel = 0; channel < source.channels; ++channel) {
            mixed += sample_at(data, source, frame, channel);
        }
        mixed /= static_cast<float>(std::max(1, source.channels));
        mixed = std::clamp(mixed, -1.0F, 1.0F);
        out[frame] = static_cast<std::int16_t>(std::lrint(mixed * 32767.0F));
    }

    return output;
}

} // namespace

WindowsWasapiCapture::WindowsWasapiCapture(
    WindowsWasapiEndpointKind endpoint_kind,
    std::string device_id,
    int device_index,
    std::string device_name_substr
)
    : endpoint_kind_(endpoint_kind),
      device_id_(std::move(device_id)),
      device_index_(device_index),
      device_name_substr_(std::move(device_name_substr)) {}

WindowsWasapiCapture::~WindowsWasapiCapture() {
    stop();
}

std::vector<AudioDeviceInfo> WindowsWasapiCapture::list_devices() {
    const bool should_uninitialize = initialize_com_for_thread();

    IMMDeviceEnumerator* enumerator = nullptr;
    IMMDevice* default_device = nullptr;
    IMMDeviceCollection* collection = nullptr;
    std::vector<AudioDeviceInfo> devices;

    try {
        throw_if_failed(CoCreateInstance(
            __uuidof(MMDeviceEnumerator),
            nullptr,
            CLSCTX_ALL,
            __uuidof(IMMDeviceEnumerator),
            reinterpret_cast<void**>(&enumerator)
        ), "CoCreateInstance(MMDeviceEnumerator)");

        const EDataFlow data_flow = data_flow_for_endpoint(endpoint_kind_);

        std::string default_id;
        if (SUCCEEDED(enumerator->GetDefaultAudioEndpoint(data_flow, eConsole, &default_device))) {
            default_id = device_id(default_device);
        }

        IMMDevice* comms_device = nullptr;
        std::string comms_id;
        if (SUCCEEDED(enumerator->GetDefaultAudioEndpoint(data_flow, eCommunications, &comms_device))) {
            comms_id = device_id(comms_device);
        }
        release_if_needed(comms_device);

        throw_if_failed(
            enumerator->EnumAudioEndpoints(data_flow, DEVICE_STATE_ACTIVE, &collection),
            "EnumAudioEndpoints"
        );

        UINT count = 0;
        throw_if_failed(collection->GetCount(&count), "IMMDeviceCollection::GetCount");
        for (UINT idx = 0; idx < count; ++idx) {
            IMMDevice* dev = nullptr;
            if (SUCCEEDED(collection->Item(idx, &dev))) {
                const std::string id = device_id(dev);
                const bool is_def = !default_id.empty() && id == default_id;
                const bool is_comms = !comms_id.empty() && id == comms_id;
                std::string role;
                if (is_def) role = "default";
                if (is_comms) role = role.empty() ? "communications" : "default+communications";
                devices.push_back({id, device_name(dev), is_def, is_comms, role, static_cast<int>(idx)});
                release_if_needed(dev);
            }
        }
    } catch (...) {
        release_if_needed(collection);
        release_if_needed(default_device);
        release_if_needed(enumerator);
        if (should_uninitialize) {
            CoUninitialize();
        }
        throw;
    }

    release_if_needed(collection);
    release_if_needed(default_device);
    release_if_needed(enumerator);
    if (should_uninitialize) {
        CoUninitialize();
    }

    return devices;
}

void WindowsWasapiCapture::start(AudioFrameCallback callback) {
    if (running_.exchange(true)) {
        return;
    }

    worker_ = std::thread([this, callback = std::move(callback)]() mutable {
        capture_loop(std::move(callback));
    });
}

void WindowsWasapiCapture::stop() {
    running_ = false;
    if (worker_.joinable()) {
        worker_.join();
    }
}

void WindowsWasapiCapture::capture_loop(AudioFrameCallback callback) {
    bool should_uninitialize = false;
    IMMDeviceEnumerator* enumerator = nullptr;
    IMMDevice* device = nullptr;
    IAudioClient* audio_client = nullptr;
    IAudioCaptureClient* capture_client = nullptr;
    WAVEFORMATEX* mix_format = nullptr;
    HANDLE mmcss_handle = nullptr;
    DWORD mmcss_task_index = 0;

    try {
        should_uninitialize = initialize_com_for_thread();

        mmcss_handle = AvSetMmThreadCharacteristicsW(L"Audio", &mmcss_task_index);

        throw_if_failed(CoCreateInstance(
            __uuidof(MMDeviceEnumerator),
            nullptr,
            CLSCTX_ALL,
            __uuidof(IMMDeviceEnumerator),
            reinterpret_cast<void**>(&enumerator)
        ), "CoCreateInstance(MMDeviceEnumerator)");

        const EDataFlow data_flow = data_flow_for_endpoint(endpoint_kind_);

        if (!device_id_.empty()) {
            const std::wstring requested_id = utf8_to_utf16(device_id_);
            throw_if_failed(enumerator->GetDevice(requested_id.c_str(), &device), "GetDevice");
        } else if (device_index_ >= 0 || !device_name_substr_.empty()) {
            IMMDeviceCollection* tmp_collection = nullptr;
            throw_if_failed(
                enumerator->EnumAudioEndpoints(data_flow, DEVICE_STATE_ACTIVE, &tmp_collection),
                "EnumAudioEndpoints(select)"
            );
            UINT count = 0;
            if (SUCCEEDED(tmp_collection->GetCount(&count))) {
                for (UINT idx = 0; idx < count; ++idx) {
                    IMMDevice* candidate = nullptr;
                    if (SUCCEEDED(tmp_collection->Item(idx, &candidate))) {
                        bool matched = false;
                        if (device_index_ >= 0 && static_cast<int>(idx) == device_index_) {
                            matched = true;
                        } else if (!device_name_substr_.empty()) {
                            matched = name_contains_icase(device_name(candidate), device_name_substr_);
                        }
                        if (matched) { device = candidate; break; }
                        release_if_needed(candidate);
                    }
                }
            }
            release_if_needed(tmp_collection);
            if (device == nullptr) {
                throw std::runtime_error(
                    "no input device matched index=" + std::to_string(device_index_) +
                    " name_substr=\"" + device_name_substr_ + "\""
                );
            }
        } else {
            HRESULT hr = enumerator->GetDefaultAudioEndpoint(data_flow, eCommunications, &device);
            if (FAILED(hr)) {
                throw_if_failed(
                    enumerator->GetDefaultAudioEndpoint(data_flow, eConsole, &device),
                    "GetDefaultAudioEndpoint(eConsole)"
                );
            }
        }
        throw_if_failed(device->Activate(
            __uuidof(IAudioClient),
            CLSCTX_ALL,
            nullptr,
            reinterpret_cast<void**>(&audio_client)
        ), "IMMDevice::Activate(IAudioClient)");

        throw_if_failed(audio_client->GetMixFormat(&mix_format), "IAudioClient::GetMixFormat");
        const SourceFormat source = describe_format(*mix_format);
        if (source.kind == SampleKind::Unsupported) {
            throw std::runtime_error("unsupported WASAPI mix format");
        }

        const REFERENCE_TIME buffer_duration = 10000000;
        throw_if_failed(audio_client->Initialize(
            AUDCLNT_SHAREMODE_SHARED,
            stream_flags_for_endpoint(endpoint_kind_),
            buffer_duration,
            0,
            mix_format,
            nullptr
        ), "IAudioClient::Initialize");

        throw_if_failed(audio_client->GetService(
            __uuidof(IAudioCaptureClient),
            reinterpret_cast<void**>(&capture_client)
        ), "IAudioClient::GetService(IAudioCaptureClient)");

        throw_if_failed(audio_client->Start(), "IAudioClient::Start");

        const AudioFormat output_format{
            source.sample_rate,
            1,
            16
        };

        while (running_) {
            std::this_thread::sleep_for(std::chrono::milliseconds(20));

            UINT32 packet_length = 0;
            throw_if_failed(capture_client->GetNextPacketSize(&packet_length), "GetNextPacketSize");

            while (packet_length != 0 && running_) {
                BYTE* data = nullptr;
                UINT32 frames = 0;
                DWORD flags = 0;

                throw_if_failed(capture_client->GetBuffer(&data, &frames, &flags, nullptr, nullptr), "GetBuffer");
                std::vector<std::byte> pcm = convert_to_mono_pcm16(data, frames, flags, source);
                throw_if_failed(capture_client->ReleaseBuffer(frames), "ReleaseBuffer");

                if (!pcm.empty()) {
                    callback(AudioFrame{
                        std::move(pcm),
                        output_format,
                        std::chrono::steady_clock::now()
                    });
                }

                throw_if_failed(capture_client->GetNextPacketSize(&packet_length), "GetNextPacketSize");
            }
        }

        audio_client->Stop();
    } catch (const std::exception& exc) {
        running_ = false;
        std::cerr << "WASAPI " << endpoint_label(endpoint_kind_)
                  << " capture error: " << exc.what() << '\n';
        if (audio_client != nullptr) {
            audio_client->Stop();
        }
    }

    if (mmcss_handle != nullptr) {
        AvRevertMmThreadCharacteristics(mmcss_handle);
    }
    if (mix_format != nullptr) {
        CoTaskMemFree(mix_format);
    }
    release_if_needed(capture_client);
    release_if_needed(audio_client);
    release_if_needed(device);
    release_if_needed(enumerator);
    if (should_uninitialize) {
        CoUninitialize();
    }
}

} // namespace grey_cardinal_agent
