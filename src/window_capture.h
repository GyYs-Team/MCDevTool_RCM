#pragma once

#ifdef _WIN32
#include <windows.h>
#include <cstdint>
#include <optional>
#include <vector>

namespace MCDevTool::Style {
    enum class CaptureResolution : std::uint8_t;
}

namespace MCDevTool::Style::Detail {
    std::optional<std::vector<uint8_t>> captureWindow(HWND hwnd, CaptureResolution resolution);
}
#endif
