# v1.6.2 更新日志：MCDK Hub 截图与 Windows 构建兼容

本版本完善 `capture_game_window` 的像素级截图与文件输出能力，同时补齐 Windows MinGW 本地构建链路，并修复运行时包清理可能沿目录联接进入源目录的重要安全问题。

## 全分辨率无损截图

- `resolution="preview"` 保持原行为：返回最高 480p 的 JPEG，适合快速视觉确认。
- `resolution="full"` 改为返回当前 Minecraft 客户区原始物理像素尺寸的无损 PNG，不再经过 JPEG 压缩。
- 全分辨率 PNG 保留编码前的 BGRA 像素颜色，不产生 JPEG 色差和压缩块。
- 截图继续使用 Windows.Graphics.Capture，可捕获被其他窗口遮挡的游戏窗口，不主动切换前台或抢占输入。

## 截图直接落盘

`capture_game_window` 新增可选参数 `output_dir`。传入绝对目录后，MCDK 会生成唯一文件名并直接写入磁盘，只向 MCP 客户端返回路径和元数据，不再返回 Base64 图片内容。

```json
{
  "resolution": "full",
  "output_dir": "C:/captures/minecraft-ui"
}
```

落盘结果包含路径、MIME、字节数和截图模式。目录不存在时自动创建；相对路径会返回参数错误。由于该参数会写文件，工具的 MCP `readOnlyHint` 已改为 `false`。

## Hub 与 bridge 工具发现

- `mcdk_stdio_bridge` 的离线 `tools/list` 已同步暴露 `resolution` 和 `output_dir`。
- bridge 保持纯转发，不在本地重新实现截图逻辑；PNG、路径元数据、结构化错误和后端响应均原样转发。
- Codex 重启后即可在首次工具发现中看到新参数，不需要先启动游戏。
- `mcdk.exe` 与 `mcdk_stdio_bridge.exe` 必须来自同一次构建，避免静态工具目录与运行时实现不一致。

## 重要安全修复

Windows MinGW 的 `std::filesystem::remove_all()` 可能把目录 Junction 当作普通目录递归处理。旧实现清理运行时行为包和资源包时存在进入 Junction 目标、删除真实 Mod 源文件的风险。

本版本改为基于 Win32 Reparse Point 属性逐项清理：

- Junction 和符号链接只删除链接节点，不遍历目标。
- 普通目录仍按预期递归删除。
- 替换已有运行时 Junction 时使用同一安全逻辑。
- 新增真实 Junction 回归测试，同时覆盖运行时包清理和重复创建联接，源目录哨兵文件必须始终保留。

## Windows 本地构建

- CMake 新增 `MC_DEV_TOOL_WINDOWS_SDK_INCLUDE_ROOT`，允许 MinGW 使用 Windows SDK NuGet 包中的 C++/WinRT 头文件。
- 补齐 `imm32`、`mswsock`、`-municode` 和 Tracy `-mlzcnt` 构建参数。
- WGC 的 COM interop 改为显式 ABI 调用，避免 MinGW Release 构建中的接口布局兼容问题。
- 本分支只保证 Windows 构建与运行，不提供 macOS 兼容。

## 验证结果

2026-09-17 在网易基岩版 `3.9.0.401155`、MCP `localhost:33043`、Tracy `43043` 上通过标准 `mcdk_hub` 验收：

- `start_instance` 在 8.4 秒内完成，没有 E22 或就绪超时。
- `get_latest_logs`、`get_latest_error_logs` 正常。
- `execute_code(direct_return=true)` 返回 `"mcp_ready"`。
- `jsonui_debugger /help` 和 `mc_input /help` 正常。
- 全分辨率截图落盘为 PNG `1279x720`，PNG 签名和窗口物理像素尺寸一致。
- 启动前后项目、公共 Mod 与 NAS 引擎仓库的跟踪文件缺失基线没有新增。

自动回归覆盖 MCP 工具 schema、stdio bridge 透明转发、JPEG/PNG 编解码、全分辨率尺寸、落盘元数据和 Junction 安全清理。
