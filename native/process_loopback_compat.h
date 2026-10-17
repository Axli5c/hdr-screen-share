#pragma once
// Windows SDK 19041 lacks these public definitions introduced in SDK 20348.
// Runtime process loopback requires Windows build 20348 or later.
#include <windows.h>
enum HssActivationType { HssActivationDefault = 0, HssActivationProcessLoopback = 1 };
enum HssProcessLoopbackMode { HssIncludeProcessTree = 0, HssExcludeProcessTree = 1 };
struct HssProcessLoopbackParams { DWORD TargetProcessId; HssProcessLoopbackMode Mode; };
struct HssActivationParams {
    HssActivationType ActivationType;
    union { HssProcessLoopbackParams ProcessLoopbackParams; };
};
constexpr wchar_t HssProcessLoopbackDevice[] = L"VAD\\Process_Loopback";
