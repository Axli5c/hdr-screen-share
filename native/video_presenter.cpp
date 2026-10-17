#include <windows.h>
#include <d3d11.h>
#include <dxgi1_4.h>
#include <wrl.h>
#include <algorithm>
#include <cstdint>
#include <memory>

using Microsoft::WRL::ComPtr;
namespace {
struct Failure { HRESULT code; };
void Check(HRESULT hr) { if (FAILED(hr)) throw Failure{hr}; }
struct Presenter {
    DWORD thread = GetCurrentThreadId();
    UINT width = 0, height = 0;
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<IDXGISwapChain1> swap;
};
}

extern "C" __declspec(dllexport) HRESULT vp_create(HWND hwnd, UINT width, UINT height, void** result) {
    if (!result) return E_POINTER;
    *result = nullptr;
    if (!IsWindow(hwnd) || !width || !height || std::max(width, height) > 3840 || std::min(width, height) > 2160)
        return E_INVALIDARG;
    try {
        auto p = std::make_unique<Presenter>();
        p->width = width; p->height = height;
        Check(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION,
            &p->device, nullptr, &p->context));
        ComPtr<IDXGIDevice> dx;
        ComPtr<IDXGIAdapter> adapter;
        ComPtr<IDXGIFactory2> factory;
        Check(p->device.As(&dx));
        Check(dx->GetAdapter(&adapter));
        Check(adapter->GetParent(IID_PPV_ARGS(&factory)));
        DXGI_SWAP_CHAIN_DESC1 desc = {};
        desc.Width = width; desc.Height = height;
        desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
        desc.SampleDesc.Count = 1;
        desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
        desc.BufferCount = 2;
        desc.SwapEffect = DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
        Check(factory->CreateSwapChainForHwnd(p->device.Get(), hwnd, &desc, nullptr, nullptr, &p->swap));
        Check(factory->MakeWindowAssociation(hwnd, DXGI_MWA_NO_ALT_ENTER));
        ComPtr<IDXGISwapChain3> color_swap;
        if (SUCCEEDED(p->swap.As(&color_swap))) {
            UINT support = 0;
            Check(color_swap->CheckColorSpaceSupport(DXGI_COLOR_SPACE_RGB_FULL_G22_NONE_P709, &support));
            if (!(support & DXGI_SWAP_CHAIN_COLOR_SPACE_SUPPORT_FLAG_PRESENT)) return E_FAIL;
            Check(color_swap->SetColorSpace1(DXGI_COLOR_SPACE_RGB_FULL_G22_NONE_P709));
        }
        *result = p.release();
        return S_OK;
    } catch (const Failure& error) { return error.code; }
      catch (...) { return E_FAIL; }
}

extern "C" __declspec(dllexport) HRESULT vp_present(void* handle, const uint8_t* pixels,
                                                     UINT width, UINT height, UINT stride) {
    auto p = static_cast<Presenter*>(handle);
    if (!p || !pixels || width != p->width || height != p->height || stride < width * 4)
        return E_INVALIDARG;
    if (GetCurrentThreadId() != p->thread) return RPC_E_WRONG_THREAD;
    ComPtr<ID3D11Texture2D> buffer;
    HRESULT hr = p->swap->GetBuffer(0, IID_PPV_ARGS(&buffer));
    if (FAILED(hr)) return hr;
    p->context->UpdateSubresource(buffer.Get(), 0, nullptr, pixels, stride, 0);
    return p->swap->Present(0, 0);
}

extern "C" __declspec(dllexport) void vp_destroy(void* handle) {
    auto p = static_cast<Presenter*>(handle);
    if (!p) return;
    p->context->ClearState();
    p->context->Flush();
    delete p;
}
