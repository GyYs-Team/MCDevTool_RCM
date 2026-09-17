# RCM 兼容分支维护

本仓库的 `main` 跟随官方 `GitHub-Zero123/MCDevTool`，`rcm` 保存 MCDK Hub、日志采集和自动化测试所需的兼容修改。不要直接在 `main` 上开发 RCM 补丁。

## 同步官方

1. 在 GitHub 或 GitHub Desktop 中获取 `upstream/main` 的最新提交，并让本地 `main` 与其一致。
2. 切换到 `rcm`，把更新后的 `main` 合并进来。
3. 只处理真实冲突；无冲突的官方修改原样保留。
4. 本地先运行 Python、工具目录和 Hub 合同测试，再推送 `rcm`。
5. 在 GitHub Actions 中手动运行 `Build Test Artifacts`，`ref` 选择 `rcm`。

兼容补丁集中在以下边界：

- 游戏内调试脚本到 MCDK 的 stdout/stderr IPC；
- MCDK 日志分类与缓冲；
- 窗口截图和 MCP 工具定义；
- `mcdk_stdio_bridge` 的离线工具目录与转发合同；
- 对应的 Python/C++ 回归测试和构建工作流。

## 构建产物

Windows Actions 产物 `mcdk-windows-x64.zip` 必须同时包含：

- `mcdk.exe`
- `mcdk_stdio_bridge.exe`

两者必须来自同一次工作流运行。bridge 在 Codex 启动时提供静态工具目录，`mcdk.exe` 在游戏运行时执行这些工具；混用不同版本可能导致 AI 看见后端尚未实现的参数或工具。

## 部署顺序

1. 关闭所有由 MCDK 启动的 Minecraft 实例。
2. 确认没有正在运行的 `mcdk.exe` 和 `mcdk_stdio_bridge.exe`。
3. 用同一份 Actions 产物中的 `mcdk.exe` 替换引擎工具目录中的版本。
4. 用同一份产物中的 `mcdk_stdio_bridge.exe` 替换 Hub 目录中的版本。
5. 重启 Codex，使首次 `tools/list` 重新读取 bridge 静态目录。

不要只替换其中一个文件，也不要从不同 Actions 运行中拼装二进制。

## 标准验收

先在没有游戏运行时确认 Hub 仍能发现完整工具表，并且调用游戏工具返回“项目未运行”的结构化结果。然后启动一个项目，依次验证：

1. `get_latest_error_logs`
2. `get_latest_logs`
3. `execute_code`，使用 `direct_return=true`
4. `jsonui_debugger`，使用 `/help`
5. `capture_game_window` 默认预览模式
6. `capture_game_window`，使用 `resolution="full"`
7. `mc_input`，使用 `/help`
8. `reload_game` 后再次执行日志和代码调用

最后完整停止并重新启动同一项目，确认 Hub 没有复用旧 IPC 会话，且后台不残留常驻 bridge 进程。

## 本地测试

使用已配置的 Python 解释器运行：

```powershell
D:\Python310\python.exe tests\debug_stdout_capture_test.py
D:\Python310\python.exe tests\stdio_bridge_test.py <mcdk_stdio_bridge.exe>
D:\Python310\python.exe -B -m unittest -v C:\path\to\rcm_tools\mcdk_mcp_hub\test_mcp_hub.py
```

截图回归 `window_capture_test` 需要带 C++/WinRT 头文件的 Windows SDK 和交互式桌面。GitHub Actions 负责用 MSVC 编译截图实现；游戏内画面仍按上面的标准验收确认。
