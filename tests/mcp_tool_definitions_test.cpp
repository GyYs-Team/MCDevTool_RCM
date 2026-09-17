#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <string>

#include <mcdk/mcp_tool_definitions.hpp>

namespace {
    void require(bool condition, const char* message) {
        if (!condition) {
            throw std::runtime_error(message);
        }
    }
}

int main() {
    try {
        const auto tool = mcdk::mcp_tool_definitions::buildCaptureGameWindowTool();
        require(tool.name == "capture_game_window", "Unexpected capture tool name");

        const auto& schema = tool.parameters_schema;
        require(schema.at("type") == "object", "Capture input schema must be an object");
        require(schema.at("properties").contains("resolution"), "Capture schema is missing resolution");
        require(schema.at("properties").contains("output_dir"), "Capture schema is missing output_dir");
        require(
            tool.annotations.read_only_hint == false,
            "Capture tool must be non-read-only because output_dir writes a file"
        );

        const auto& resolution = schema.at("properties").at("resolution");
        require(resolution.at("type") == "string", "Capture resolution must be a string");
        require(
            resolution.at("enum") == nlohmann::json::array({"preview", "full"}),
            "Capture resolution enum changed"
        );

        const auto required = schema.value("required", nlohmann::json::array());
        require(
            std::find(required.begin(), required.end(), "resolution") == required.end(),
            "Capture resolution must remain optional"
        );
        require(
            std::find(required.begin(), required.end(), "output_dir") == required.end(),
            "Capture output_dir must remain optional"
        );

        const auto allTools = mcdk::mcp_tool_definitions::buildAllTools();
        require(
            std::ranges::any_of(allTools, [](const auto& candidate) {
                return candidate.name == "capture_game_window"
                    && candidate.parameters_schema.at("properties").contains("resolution")
                    && candidate.parameters_schema.at("properties").contains("output_dir");
            }),
            "Static bridge catalog does not expose the complete capture schema"
        );

        std::cout << "PASS: capture_game_window exposes optional preview/full resolution and output_dir\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
