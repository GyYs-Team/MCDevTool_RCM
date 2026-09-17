#include <mcdevtool/env.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

namespace {
    bool setAppData(const std::filesystem::path& path) {
        return _putenv_s("APPDATA", path.string().c_str()) == 0;
    }

    bool writeSentinel(const std::filesystem::path& path) {
        std::filesystem::create_directories(path.parent_path());
        std::ofstream output(path, std::ios::binary);
        output << "source must survive runtime cleanup";
        return output.good();
    }
}

int main() {
    const auto testRoot = std::filesystem::temp_directory_path()
                        / (L"mcdev-runtime-cleanup-" + std::to_wstring(GetCurrentProcessId()));
    const auto appData = testRoot / "appdata";
    const auto sourcePack = testRoot / "source-pack";
    const auto sentinel = sourcePack / "nested" / "sentinel.txt";
    const auto behaviorPacks = appData / "MinecraftPE_Netease" / "games" / "com.netease" / "behavior_packs";
    const auto runtimeLink = behaviorPacks / "linked-pack";
    const auto resourcePacks = appData / "MinecraftPE_Netease" / "games" / "com.netease" / "resource_packs";

    std::filesystem::remove_all(testRoot);
    if (!writeSentinel(sentinel) || !setAppData(appData)) {
        std::cerr << "failed to prepare runtime cleanup test\n";
        return 1;
    }
    if (!MCDevTool::createDirectoryJunction(sourcePack, runtimeLink)) {
        std::cerr << "failed to create test junction\n";
        return 1;
    }
    if (!MCDevTool::createDirectoryJunction(sourcePack, runtimeLink) || !std::filesystem::is_regular_file(sentinel)) {
        std::cerr << "replacing a junction modified its source\n";
        return 1;
    }
    std::filesystem::create_directories(resourcePacks / "normal-pack" / "nested");
    std::ofstream(resourcePacks / "normal-pack" / "nested" / "runtime.txt") << "runtime";

    MCDevTool::cleanRuntimePacks();

    const bool sourceSurvived = std::filesystem::is_regular_file(sentinel);
    const bool linkRemoved = !std::filesystem::exists(runtimeLink);
    const bool behaviorRootRemoved = !std::filesystem::exists(behaviorPacks);
    const bool resourceRootRemoved = !std::filesystem::exists(resourcePacks);
    if (!sourceSurvived || !linkRemoved || !behaviorRootRemoved || !resourceRootRemoved) {
        std::cerr << "runtime cleanup followed a junction or left runtime data behind\n";
        return 1;
    }

    std::filesystem::remove_all(testRoot);
    return 0;
}
