#!/usr/bin/env python3
"""Verify the stdio proxy against a local fake MCP backend, without launching Minecraft."""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


IMAGE = {"type": "image", "mimeType": "image/jpeg", "data": "YWJj" * 262144}
PNG_IMAGE = {"type": "image", "mimeType": "image/png", "data": "YWJj" * 262144}
RESULT = {
    "isError": False,
    "content": [IMAGE, {"type": "text", "text": "截图后的日志"}],
    "structuredContent": {"ok": True, "data": {"logs": ["测试日志"]}},
}
PNG_RESULT = {
    "isError": False,
    "content": [PNG_IMAGE, {"type": "text", "text": "已落盘"}],
    "structuredContent": {
        "ok": True,
        "path": "C:/captures/minecraft_capture_full.png",
        "mime_type": "image/png",
    },
}
FAILURE = {
    "isError": True,
    "content": [{"type": "text", "text": "backend failure"}],
    "structuredContent": {"ok": False, "error": {"code": "FOCUS_LOST"}},
}


class Backend(BaseHTTPRequestHandler):
    calls = []
    requests = []
    offline = False

    def log_message(self, *_args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(request["method"])
        if self.offline:
            self.send_response(503)
            self.end_headers()
            return
        response = {"jsonrpc": "2.0", "id": request.get("id"), "result": {}}
        if request["method"] == "tools/call":
            params = request["params"]
            self.calls.append(params)
            mode = params["arguments"].get("op")
            if params["name"] == "capture_game_window":
                response["result"] = PNG_RESULT
            else:
                response["result"] = FAILURE if mode == "/failure" else RESULT
            if mode == "/missing":
                response.pop("result")
                response["error"] = {"code": -32601, "message": "Tool not found"}
            if mode == "/disconnect":
                type(self).offline = True
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Mcp-Session-Id", "bridge-test")
        self.end_headers()
        self.wfile.write(payload)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    requests = []

    def add(method, params=None):
        requests.append({"jsonrpc": "2.0", "id": len(requests) + 1, "method": method, "params": params or {}})

    def call(name, arguments):
        add("tools/call", {"name": name, "arguments": arguments})

    add("initialize")
    add("tools/list")
    call("capture_game_window", {"resolution": "full", "output_dir": "C:/captures"})
    call("mc_input", {"op": "/help"})
    call("mc_input", {"op": "/run"})
    call("mc_profiler", {"op": "/guide"})
    call("mc_input", {"op": "/failure"})
    call("mc_profiler", {"op": "/missing"})
    call("mc_input", {"op": "/disconnect"})
    call("mc_input", {"op": "/help"})
    call("mc_profiler", {"op": "/help"})
    add("tools/list")
    add("ping")
    wire = "".join(json.dumps(request) + "\n" for request in requests)
    try:
        try:
            completed = subprocess.run(
                [sys.argv[1], "--host", "127.0.0.1", "--port", str(server.server_port)],
                input=wire,
                capture_output=True,
                encoding="utf-8",
                timeout=30,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as error:
            partial_stdout = error.stdout or ""
            if isinstance(partial_stdout, bytes):
                partial_stdout = partial_stdout.decode("utf-8", errors="replace")
            reply_ids = []
            for line in partial_stdout.splitlines():
                try:
                    reply_ids.append(json.loads(line).get("id"))
                except json.JSONDecodeError:
                    pass
            raise AssertionError(
                f"bridge timed out after replies {reply_ids}; backend requests={Backend.requests}"
            ) from error
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [reply["id"] for reply in replies] == list(range(1, len(requests) + 1))
    results = [reply["result"] for reply in replies]
    tools = {tool["name"]: tool for tool in results[1]["tools"]}
    names = set(tools)
    assert len(names) == 9 and {"mc_input", "mc_profiler", "capture_game_window"} <= names
    capture_tool = tools["capture_game_window"]
    capture_resolution = capture_tool["inputSchema"]["properties"]["resolution"]
    assert capture_resolution["enum"] == ["preview", "full"]
    assert "output_dir" in capture_tool["inputSchema"]["properties"]
    assert capture_tool["annotations"]["readOnlyHint"] is False
    assert results[2] == PNG_RESULT, "PNG path result must pass through unchanged"
    for index in (3, 4, 5, 8):
        assert results[index] == RESULT, "image, text and structured content must pass through unchanged"
    assert results[6] == FAILURE, "backend tool errors must remain unchanged"
    assert results[7]["structuredContent"]["error"]["code"] == "BACKEND_TOOL_UNAVAILABLE"
    for index in (9, 10):
        body = results[index]["structuredContent"]
        assert body["ok"] is False and body["error"]["code"] == "BACKEND_UNAVAILABLE"
        assert body["op"] == "/help", "offline help must not execute a local backend"
    assert results[11] == results[1], "the offline tool catalog must remain available"
    assert results[12] == {}, "the bridge must still handle requests after backend failure"
    assert Backend.calls == [request["params"] for request in requests[2:9]]
    print("PASS: tool catalog / JPEG and PNG forwarding / file metadata / backend errors / offline recovery")


if __name__ == "__main__":
    main()
