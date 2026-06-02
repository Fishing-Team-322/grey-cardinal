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

WindowsWasapiLoopbackCapture::~WindowsWasapiLoopbackCapture() {
    stop();
}

std::vector<AudioDeviceInfo> WindowsWasapiLoopbackCapture::list_devices() {
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

        std::string default_id;
        if (SUCCEEDED(enumerator->GetDefaultAudioEndpoint(eRender, eConsole, &default_device))) {
            default_id = device_id(default_device);
        }

        throw_if_failed(enumerator->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &collection), "EnumAudioEndpoints");

        UINT count = 0;
        throw_if_failed(collection->GetCount(&count), "IMMDeviceCollection::GetCount");
        for (UINT index = 0; index < count; ++index) {
            IMMDevice* device = nullptr;
            if (SUCCEEDED(collection->Item(index, &device))) {
                const std::string id = device_id(device);
                devices.push_back({
                    id,
                    device_name(device),
                    !default_id.empty() && id == default_id
                });
                release_if_needed(device);
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

void WindowsWasapiLoopbackCapture::start(AudioFrameCallback callback) {
    if (running_.exchange(true)) {
        return;
    }

    worker_ = std::thread([this, callback = std::move(callback)]() mutable {
        capture_loop(std::move(callback));
    });
}

void WindowsWasapiLoopbackCapture::stop() {
    running_ = false;
    if (worker_.joinable()) {
        worker_.join();
    }
}

void WindowsWasapiLoopbackCapture::capture_loop(AudioFrameCallback callback) {
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

        throw_if_failed(enumerator->GetDefaultAudioEndpoint(eRender, eConsole, &device), "GetDefaultAudioEndpoint");
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
            AUDCLNT_STREAMFLAGS_LOOPBACK,
            buffer_duration,
            0,
            mix_format,
            nullptr
        ), "IAudioClient::Initialize(loopback)");

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
        std::cerr << "WASAPI capture error: " << exc.what() << '\n';
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
