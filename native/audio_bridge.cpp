#include "audio_bridge.h"
#include "audio_mixer.h"
#include "process_loopback_compat.h"
#include <audioclient.h>
#include <audiopolicy.h>
#include <mmdeviceapi.h>
#include <functiondiscoverykeys_devpkey.h>
#include <propvarutil.h>
#include <tlhelp32.h>
#include <wrl.h>
#include <atomic>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>

using Microsoft::WRL::ComPtr;
struct Failure { HRESULT code; };
static void Check(HRESULT hr) { if (FAILED(hr)) throw Failure{hr}; }
struct ComScope {
    HRESULT status = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    ComScope() { if (status != RPC_E_CHANGED_MODE) Check(status); }
    ~ComScope() { if (SUCCEEDED(status)) CoUninitialize(); }
};
static ComPtr<IMMDeviceEnumerator> Enumerator() {
    ComPtr<IMMDeviceEnumerator> result;
    Check(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, IID_PPV_ARGS(&result)));
    return result;
}
static std::wstring DeviceId(IMMDevice* device) {
    LPWSTR text = nullptr;
    Check(device->GetId(&text));
    std::wstring result(text); CoTaskMemFree(text); return result;
}
static std::wstring DeviceName(IMMDevice* device) {
    ComPtr<IPropertyStore> store; Check(device->OpenPropertyStore(STGM_READ, &store));
    PROPVARIANT value; PropVariantInit(&value);
    Check(store->GetValue(PKEY_Device_FriendlyName, &value));
    std::wstring result = value.vt == VT_LPWSTR ? value.pwszVal : L"";
    PropVariantClear(&value); return result;
}
static WAVEFORMATEX Format() {
    WAVEFORMATEX value{};
    value.wFormatTag = WAVE_FORMAT_IEEE_FLOAT; value.nChannels = 2;
    value.nSamplesPerSec = 48000; value.wBitsPerSample = 32;
    value.nBlockAlign = 8; value.nAvgBytesPerSec = 384000;
    return value;
}
static uint64_t HandleCreationTime(HANDLE process) {
    FILETIME created{}, ended{}, kernel{}, user{};
    BOOL ok = GetProcessTimes(process, &created, &ended, &kernel, &user);
    return ok ? (uint64_t(created.dwHighDateTime) << 32) | created.dwLowDateTime : 0;
}
static uint64_t CreationTime(DWORD pid) {
    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!process) return 0;
    uint64_t result = HandleCreationTime(process);
    CloseHandle(process); return result;
}
static bool ConfirmedExited(DWORD pid) {
    HANDLE process = OpenProcess(SYNCHRONIZE, FALSE, pid);
    if (!process) return GetLastError() == ERROR_INVALID_PARAMETER;
    bool exited = WaitForSingleObject(process, 0) == WAIT_OBJECT_0;
    CloseHandle(process); return exited;
}
static DWORD AudioServicePid() {
    // A render session owned by Windows Audio may relay device monitoring.
    // Never treat the audio service as an application source (mic/relay risk).
    SC_HANDLE manager = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT);
    if (!manager) return 0;
    SC_HANDLE service = OpenServiceW(manager, L"Audiosrv", SERVICE_QUERY_STATUS);
    SERVICE_STATUS_PROCESS status{}; DWORD needed = 0;
    BOOL ok = service && QueryServiceStatusEx(service, SC_STATUS_PROCESS_INFO,
        reinterpret_cast<BYTE*>(&status), sizeof(status), &needed);
    if (service) CloseServiceHandle(service);
    CloseServiceHandle(manager);
    return ok ? status.dwProcessId : 0;
}
static std::vector<AbProcessInfo> Processes() {
    std::vector<AbProcessInfo> result;
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) throw Failure{HRESULT_FROM_WIN32(GetLastError())};
    PROCESSENTRY32W item{}; item.dwSize = sizeof(item);
    if (Process32FirstW(snapshot, &item)) do {
        uint64_t created = CreationTime(item.th32ProcessID);
        if (!created) continue;
        AbProcessInfo process{}; process.pid = item.th32ProcessID;
        process.parent_pid = item.th32ParentProcessID; process.created_at = created;
        wcsncpy_s(process.image_name, item.szExeFile, _TRUNCATE);
        result.push_back(process);
    } while (Process32NextW(snapshot, &item));
    CloseHandle(snapshot); return result;
}
template<class T> static HRESULT CopyList(const std::vector<T>& values, T* out, uint32_t capacity, uint32_t* count) {
    if (!count || (capacity && !out)) return E_POINTER;
    *count = static_cast<uint32_t>(values.size());
    if (capacity < values.size()) return HRESULT_FROM_WIN32(ERROR_INSUFFICIENT_BUFFER);
    if (!values.empty()) std::copy(values.begin(), values.end(), out);
    return S_OK;
}

class Activation : public Microsoft::WRL::RuntimeClass<
    Microsoft::WRL::RuntimeClassFlags<Microsoft::WRL::ClassicCom>,
    Microsoft::WRL::FtmBase, IActivateAudioInterfaceCompletionHandler> {
public:
    HANDLE done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HRESULT status = E_PENDING;
    ComPtr<IAudioClient> client;
    ~Activation() { if (done) CloseHandle(done); }
    STDMETHOD(ActivateCompleted)(IActivateAudioInterfaceAsyncOperation* operation) override {
        ComPtr<IUnknown> object;
        HRESULT activation = E_FAIL;
        status = operation->GetActivateResult(&activation, &object);
        if (SUCCEEDED(status)) status = activation;
        if (SUCCEEDED(status)) status = object.As(&client);
        SetEvent(done); return S_OK;
    }
};
struct Capture {
    uint32_t pid = 0;
    uint64_t created = 0;
    HANDLE process = nullptr;
    ComPtr<IAudioClient> client;
    ComPtr<IAudioCaptureClient> reader;
    ~Capture() { if (client) client->Stop(); if (process) CloseHandle(process); }
};
static std::unique_ptr<Capture> OpenCapture(const AbProcessInfo& process, std::atomic<bool>& stop) {
    if (process.pid == GetCurrentProcessId())
        throw Failure{E_ACCESSDENIED};
    auto result = std::make_unique<Capture>();
    result->process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, process.pid);
    if (!result->process || HandleCreationTime(result->process) != process.created_at)
        throw Failure{E_ACCESSDENIED};
    auto completion = Microsoft::WRL::Make<Activation>();
    if (!completion || !completion->done) throw Failure{E_OUTOFMEMORY};
    HssActivationParams params{}; params.ActivationType = HssActivationProcessLoopback;
    params.ProcessLoopbackParams = {process.pid, HssIncludeProcessTree};
    PROPVARIANT value{}; value.vt = VT_BLOB;
    value.blob.cbSize = sizeof(params); value.blob.pBlobData = reinterpret_cast<BYTE*>(&params);
    ComPtr<IActivateAudioInterfaceAsyncOperation> operation;
    Check(ActivateAudioInterfaceAsync(HssProcessLoopbackDevice, __uuidof(IAudioClient), &value, completion.Get(), &operation));
    unsigned waits = 0;
    while (WaitForSingleObject(completion->done, 20) == WAIT_TIMEOUT) {
        if (stop || ++waits > 400) throw Failure{HRESULT_FROM_WIN32(ERROR_TIMEOUT)};
    }
    Check(completion->status);
    result->pid = process.pid; result->created = process.created_at;
    result->client = completion->client;
    auto format = Format();
    Check(result->client->Initialize(AUDCLNT_SHAREMODE_SHARED,
        AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
        1000000, 0, &format, nullptr));
    Check(result->client->GetService(IID_PPV_ARGS(&result->reader)));
    Check(result->client->Start()); return result;
}
struct Relay {
    std::wstring endpoint;
    std::atomic<bool> stop{false};
    std::mutex mutex;
    std::vector<AbProcessInfo> requested;
    uint64_t generation = 0;
    AbStats stats{};
    HANDLE ready = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    std::atomic<HRESULT> init{E_PENDING};
    std::thread thread;
    ~Relay() { stop = true; if (thread.joinable()) thread.join(); if (ready) CloseHandle(ready); }
    void Run() noexcept {
        std::unique_ptr<ComScope> com;
        ComPtr<IAudioClient> output;
        try {
            com = std::make_unique<ComScope>();
            auto enumerator = Enumerator();
            ComPtr<IMMDevice> device; Check(enumerator->GetDevice(endpoint.c_str(), &device));
            auto name = DeviceName(device.Get());
            // Accept only the explicitly selected cable playback endpoint.
            if (name.find(L"CABLE Input") == std::wstring::npos || name.find(L"VB-Audio") == std::wstring::npos)
                throw Failure{E_ACCESSDENIED};
            ComPtr<IMMEndpoint> direction; Check(device.As(&direction));
            EDataFlow flow; Check(direction->GetDataFlow(&flow));
            if (flow != eRender) throw Failure{E_ACCESSDENIED};
            Check(device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, &output));
            auto format = Format();
            Check(output->Initialize(AUDCLNT_SHAREMODE_SHARED,
                AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
                300000, 0, &format, nullptr));
            ComPtr<IAudioRenderClient> writer; Check(output->GetService(IID_PPV_ARGS(&writer)));
            UINT32 capacity = 0; Check(output->GetBufferSize(&capacity));
            Check(output->Start());
            init = S_OK; SetEvent(ready);
            AudioMixer mixer(2, 4800);
            std::vector<std::unique_ptr<Capture>> captures;
            uint64_t applied = 0;
            while (!stop) {
                std::vector<AbProcessInfo> roots;
                uint64_t next;
                { std::lock_guard<std::mutex> lock(mutex); next = generation; if (next != applied) roots = requested; }
                if (next != applied) {
                    captures.clear(); mixer.clear();
                    for (const auto& root : roots) captures.push_back(OpenCapture(root, stop));
                    applied = next;
                }
                for (auto iterator = captures.begin(); iterator != captures.end();) {
                    auto& capture = *iterator;
                    DWORD state = WaitForSingleObject(capture->process, 0);
                    if (state == WAIT_OBJECT_0) {
                        mixer.remove(capture->pid);
                        iterator = captures.erase(iterator);
                        continue;
                    }
                    if (state != WAIT_TIMEOUT) throw Failure{E_ACCESSDENIED};
                    UINT32 available = 0; Check(capture->reader->GetNextPacketSize(&available));
                    while (available) {
                        BYTE* data = nullptr; UINT32 frames = 0; DWORD flags = 0;
                        Check(capture->reader->GetBuffer(&data, &frames, &flags, nullptr, nullptr));
                        mixer.push(capture->pid, flags & AUDCLNT_BUFFERFLAGS_SILENT ? nullptr : reinterpret_cast<float*>(data), frames);
                        Check(capture->reader->ReleaseBuffer(frames));
                        Check(capture->reader->GetNextPacketSize(&available));
                    }
                    ++iterator;
                }
                UINT32 padding = 0; Check(output->GetCurrentPadding(&padding));
                UINT32 available = capacity - std::min(padding, capacity);
                if (available) {
                    BYTE* data = nullptr; Check(writer->GetBuffer(available, &data));
                    mixer.mix(reinterpret_cast<float*>(data), available);
                    Check(writer->ReleaseBuffer(available, 0));
                    std::lock_guard<std::mutex> lock(mutex);
                    stats.output_frames += available;
                    stats.queued_frames = static_cast<uint32_t>(mixer.queued_frames());
                    stats.overflows = mixer.overflows();
                }
                Sleep(3);
            }
            output->Stop();
        } catch (const Failure& error) {
            std::lock_guard<std::mutex> lock(mutex);
            stats.last_hresult = error.code; init = error.code;
            if (output) output->Stop(); SetEvent(ready);
        } catch (...) {
            std::lock_guard<std::mutex> lock(mutex);
            stats.last_hresult = E_FAIL; init = E_FAIL;
            if (output) output->Stop(); SetEvent(ready);
        }
    }
};

AB_API ab_list_endpoints(AbEndpointInfo* buffer, uint32_t capacity, uint32_t* count) {
    try {
        ComScope com; auto enumerator = Enumerator();
        ComPtr<IMMDeviceCollection> devices;
        Check(enumerator->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &devices));
        UINT length = 0; Check(devices->GetCount(&length));
        std::vector<AbEndpointInfo> result;
        std::wstring defaults[3];
        for (int role = 0; role < 3; ++role) {
            ComPtr<IMMDevice> device;
            if (SUCCEEDED(enumerator->GetDefaultAudioEndpoint(eRender, static_cast<ERole>(role), &device))) defaults[role] = DeviceId(device.Get());
        }
        for (UINT index = 0; index < length; ++index) {
            ComPtr<IMMDevice> device; Check(devices->Item(index, &device));
            auto id = DeviceId(device.Get()), name = DeviceName(device.Get());
            AbEndpointInfo item{};
            if (id.size() >= _countof(item.id) || name.size() >= _countof(item.name)) throw Failure{E_INVALIDARG};
            wcscpy_s(item.id, id.c_str()); wcscpy_s(item.name, name.c_str());
            for (int role = 0; role < 3; ++role) if (id == defaults[role]) item.default_roles |= 1u << role;
            result.push_back(item);
        }
        return CopyList(result, buffer, capacity, count);
    } catch (const Failure& error) { return error.code; } catch (...) { return E_FAIL; }
}
AB_API ab_list_processes(AbProcessInfo* buffer, uint32_t capacity, uint32_t* count) {
    try { return CopyList(Processes(), buffer, capacity, count); }
    catch (const Failure& error) { return error.code; } catch (...) { return E_FAIL; }
}
AB_API ab_list_audio_pids(uint32_t* buffer, uint32_t capacity, uint32_t* count) {
    try {
        ComScope com; auto enumerator = Enumerator();
        ComPtr<IMMDeviceCollection> devices; Check(enumerator->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &devices));
        UINT length = 0; Check(devices->GetCount(&length));
        std::set<uint32_t> pids;
        bool skippedSystemSounds = false;
        DWORD audioService = AudioServicePid();
        for (UINT index = 0; index < length; ++index) {
            ComPtr<IMMDevice> device; Check(devices->Item(index, &device));
            ComPtr<IAudioSessionManager2> manager;
            Check(device->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, &manager));
            ComPtr<IAudioSessionEnumerator> sessions; Check(manager->GetSessionEnumerator(&sessions));
            int countSessions = 0; Check(sessions->GetCount(&countSessions));
            for (int item = 0; item < countSessions; ++item) {
                ComPtr<IAudioSessionControl> session; Check(sessions->GetSession(item, &session));
                AudioSessionState state; Check(session->GetState(&state));
                if (state != AudioSessionStateActive) continue;
                ComPtr<IAudioSessionControl2> control; Check(session.As(&control));
                HRESULT systemSounds = control->IsSystemSoundsSession();
                Check(systemSounds);
                if (systemSounds == S_OK) {
                    // System sounds belong to Audiosrv, not an isolatable app.
                    skippedSystemSounds = true;
                    continue;
                }
                DWORD pid = 0;
                HRESULT processResult = control->GetProcessId(&pid);
                Check(processResult);
                if ((audioService && pid == audioService) || processResult != S_OK) {
                    skippedSystemSounds = true;
                    continue;
                }
                if (pid && !ConfirmedExited(pid)) pids.insert(pid);
            }
        }
        HRESULT result = CopyList(std::vector<uint32_t>(pids.begin(), pids.end()), buffer, capacity, count);
        return result == S_OK && skippedSystemSounds ? S_FALSE : result;
    } catch (const Failure& error) { return error.code; } catch (...) { return E_FAIL; }
}
AB_API ab_open(const wchar_t* endpoint_id, AbHandle* out) {
    if (!endpoint_id || !out) return E_POINTER;
    *out = nullptr;
    try {
        auto relay = std::make_unique<Relay>();
        if (!relay->ready) return E_OUTOFMEMORY;
        relay->endpoint = endpoint_id;
        relay->thread = std::thread([instance = relay.get()] { instance->Run(); });
        if (WaitForSingleObject(relay->ready, 10000) != WAIT_OBJECT_0) return HRESULT_FROM_WIN32(ERROR_TIMEOUT);
        Check(relay->init); *out = relay.release(); return S_OK;
    } catch (const Failure& error) { return error.code; } catch (...) { return E_FAIL; }
}
AB_API ab_set_sources(AbHandle handle, const AbProcessInfo* roots, uint32_t count) {
    if (!handle || (count && !roots)) return E_POINTER;
    if (count > 1024) return E_INVALIDARG;
    try {
        auto relay = static_cast<Relay*>(handle);
        std::lock_guard<std::mutex> lock(relay->mutex);
        if (FAILED(relay->stats.last_hresult)) return relay->stats.last_hresult;
        relay->requested.clear();
        if (count) relay->requested.assign(roots, roots + count);
        ++relay->generation; return S_OK;
    } catch (...) { return E_FAIL; }
}
AB_API ab_get_stats(AbHandle handle, AbStats* out) {
    if (!handle || !out) return E_POINTER;
    auto relay = static_cast<Relay*>(handle);
    std::lock_guard<std::mutex> lock(relay->mutex); *out = relay->stats; return S_OK;
}
AB_API ab_stop(AbHandle handle) {
    if (!handle) return S_OK;
    try { delete static_cast<Relay*>(handle); return S_OK; } catch (...) { return E_FAIL; }
}

AB_API ab_probe_capture(const wchar_t* endpoint_id, uint32_t seconds, float* samples,
                        uint32_t capacity_frames, uint32_t* written_frames) {
    if (!endpoint_id || !samples || !written_frames) return E_POINTER;
    *written_frames = 0;
    if (!seconds || seconds > 10 || capacity_frames < seconds * 48000) return E_INVALIDARG;
    try {
        ComScope com; auto enumerator = Enumerator();
        ComPtr<IMMDevice> device; Check(enumerator->GetDevice(endpoint_id, &device));
        auto name = DeviceName(device.Get());
        if (name.find(L"CABLE Input") == std::wstring::npos || name.find(L"VB-Audio") == std::wstring::npos)
            return E_ACCESSDENIED;
        ComPtr<IAudioClient> client;
        Check(device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, &client));
        auto format = Format();
        Check(client->Initialize(AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
            1000000, 0, &format, nullptr));
        ComPtr<IAudioCaptureClient> reader; Check(client->GetService(IID_PPV_ARGS(&reader)));
        Check(client->Start());
        ULONGLONG deadline = GetTickCount64() + (seconds + 2) * 1000;
        const uint32_t target = seconds * 48000;
        while (*written_frames < target && GetTickCount64() < deadline) {
            UINT32 available = 0; Check(reader->GetNextPacketSize(&available));
            while (available && *written_frames < target) {
                BYTE* bytes = nullptr; UINT32 frames = 0; DWORD flags = 0;
                Check(reader->GetBuffer(&bytes, &frames, &flags, nullptr, nullptr));
                const uint32_t copy = std::min(frames, target - *written_frames);
                float* destination = samples + *written_frames * 2;
                if (flags & AUDCLNT_BUFFERFLAGS_SILENT) std::fill(destination, destination + copy * 2, 0.0f);
                else std::copy(reinterpret_cast<float*>(bytes), reinterpret_cast<float*>(bytes) + copy * 2, destination);
                *written_frames += copy;
                Check(reader->ReleaseBuffer(frames));
                Check(reader->GetNextPacketSize(&available));
            }
            Sleep(3);
        }
        client->Stop();
        return *written_frames == target ? S_OK : HRESULT_FROM_WIN32(ERROR_TIMEOUT);
    } catch (const Failure& error) { return error.code; } catch (...) { return E_FAIL; }
}
