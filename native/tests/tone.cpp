#define NOMINMAX
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <wrl.h>
#include <cmath>
#include <cstdlib>
#include <iostream>
using Microsoft::WRL::ComPtr;
static void Check(HRESULT hr) { if (FAILED(hr)) throw hr; }
int wmain(int argc, wchar_t** argv) {
    if (argc != 3) return 2;
    double frequency = _wtof(argv[1]); int seconds = _wtoi(argv[2]);
    if (frequency < 100 || frequency > 5000 || seconds < 1 || seconds > 30) return 2;
    HRESULT init = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(init)) return 3;
    int result = 0;
    try {
        ComPtr<IMMDeviceEnumerator> devices;
        Check(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, IID_PPV_ARGS(&devices)));
        ComPtr<IMMDevice> device; Check(devices->GetDefaultAudioEndpoint(eRender, eConsole, &device));
        ComPtr<IAudioClient> client; Check(device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, &client));
        WAVEFORMATEX format{}; format.wFormatTag = WAVE_FORMAT_IEEE_FLOAT; format.nChannels = 2;
        format.nSamplesPerSec = 48000; format.wBitsPerSample = 32; format.nBlockAlign = 8; format.nAvgBytesPerSec = 384000;
        Check(client->Initialize(AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
            300000, 0, &format, nullptr));
        ComPtr<IAudioRenderClient> render; Check(client->GetService(IID_PPV_ARGS(&render)));
        UINT32 capacity = 0; Check(client->GetBufferSize(&capacity)); Check(client->Start());
        uint64_t position = 0, total = uint64_t(seconds) * 48000;
        while (position < total) {
            UINT32 padding = 0; Check(client->GetCurrentPadding(&padding));
            UINT32 count = static_cast<UINT32>(std::min<uint64_t>(capacity - padding, total - position));
            if (count) {
                BYTE* bytes = nullptr; Check(render->GetBuffer(count, &bytes));
                auto samples = reinterpret_cast<float*>(bytes);
                for (UINT32 index = 0; index < count; ++index) {
                    float value = static_cast<float>(0.06 * sin(6.283185307179586 * frequency * double(position + index) / 48000));
                    samples[index * 2] = samples[index * 2 + 1] = value;
                }
                Check(render->ReleaseBuffer(count, 0)); position += count;
            }
            Sleep(3);
        }
        Sleep(40); client->Stop();
    } catch (HRESULT error) { std::cerr << "Tone failed: " << std::hex << error << '\n'; result = 1; }
    CoUninitialize(); return result;
}
