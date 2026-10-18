#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <cstdint>
#include <windows.h>
#define AB_API extern "C" __declspec(dllexport) HRESULT __cdecl
using AbHandle = void*;
struct AbProcessInfo {
    uint32_t pid, parent_pid;
    uint64_t created_at;
    wchar_t image_name[260];
};
struct AbStats {
    uint64_t output_frames;
    uint32_t queued_frames;
    uint64_t overflows;
    int32_t last_hresult;
};
struct AbEndpointInfo {
    wchar_t id[512];
    wchar_t name[256];
    uint32_t default_roles;
};
AB_API ab_open(const wchar_t* endpoint_id, AbHandle* out);
AB_API ab_list_processes(AbProcessInfo* buffer, uint32_t capacity, uint32_t* count);
AB_API ab_list_audio_pids(uint32_t* buffer, uint32_t capacity, uint32_t* count);
AB_API ab_list_endpoints(AbEndpointInfo* buffer, uint32_t capacity, uint32_t* count);
AB_API ab_list_inactive_endpoints(AbEndpointInfo* buffer, uint32_t capacity, uint32_t* count);
AB_API ab_set_sources(AbHandle handle, const AbProcessInfo* roots, uint32_t count);
AB_API ab_get_stats(AbHandle handle, AbStats* out);
AB_API ab_stop(AbHandle handle);
// Diagnostic use only: bounded in-memory recording of the selected virtual cable.
AB_API ab_probe_capture(const wchar_t* endpoint_id, uint32_t seconds, float* samples,
                        uint32_t capacity_frames, uint32_t* written_frames);
