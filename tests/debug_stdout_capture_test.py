# -*- coding: utf-8 -*-
import importlib.util
import pathlib
import unittest


MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "mods"
    / "INCLUDE_TEST_MOD"
    / "DEBUG_ENV_SCRIPT"
    / "StdoutCapture.py"
)
SPEC = importlib.util.spec_from_file_location("mcdk_stdout_capture", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SET_LOG_SENDER = MODULE.SET_LOG_SENDER
STD_OUT_WRAPPER = MODULE.STD_OUT_WRAPPER


class FakeStream(object):
    def __init__(self):
        self.writes = []
        self.flush_count = 0

    def write(self, data):
        self.writes.append(data)

    def flush(self):
        self.flush_count += 1


class StdoutCaptureTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        SET_LOG_SENDER(lambda channel, line: self.sent.append((channel, line)) or True)

    def tearDown(self):
        SET_LOG_SENDER(None)

    def test_forwards_stdout_once_and_preserves_game_output(self):
        game_output = FakeStream()
        wrapper = STD_OUT_WRAPPER(game_output, "stdout")

        wrapper.write("hello\n")

        self.assertEqual(game_output.writes, ["[Python] hello\n"])
        self.assertEqual(self.sent, [("stdout", "[Python] hello")])

    def test_forwards_stderr_to_error_channel(self):
        game_output = FakeStream()
        wrapper = STD_OUT_WRAPPER(game_output, "stderr")

        wrapper.write("failure\n")

        self.assertEqual(game_output.writes, ["[Python] failure\n"])
        self.assertEqual(self.sent, [("stderr", "[Python] failure")])

    def test_combines_fragmented_writes_and_escapes_nul(self):
        game_output = FakeStream()
        wrapper = STD_OUT_WRAPPER(game_output, "stdout")

        wrapper.write("hel")
        wrapper.write("lo\x00")
        wrapper.write(" world\n")

        self.assertEqual(game_output.writes, ["[Python] hello\\0 world\n"])
        self.assertEqual(self.sent, [("stdout", "[Python] hello\\0 world")])

    def test_supports_unicode(self):
        game_output = FakeStream()
        wrapper = STD_OUT_WRAPPER(game_output, "stdout")

        wrapper.write("中文日志\n")

        self.assertEqual(game_output.writes, ["[Python] 中文日志\n"])
        self.assertEqual(self.sent, [("stdout", "[Python] 中文日志")])

    def test_flush_emits_partial_line(self):
        game_output = FakeStream()
        wrapper = STD_OUT_WRAPPER(game_output, "stdout")

        wrapper.write("partial")
        wrapper.flush()

        self.assertEqual(game_output.writes, ["[Python] partial"])
        self.assertEqual(game_output.flush_count, 1)
        self.assertEqual(self.sent, [("stdout", "[Python] partial")])

    def test_no_connection_still_preserves_game_output(self):
        SET_LOG_SENDER(None)
        game_output = FakeStream()
        wrapper = STD_OUT_WRAPPER(game_output, "stdout")

        wrapper.write("offline\n")

        self.assertEqual(game_output.writes, ["[Python] offline\n"])
        self.assertEqual(self.sent, [])

    def test_sender_failure_does_not_break_print(self):
        def fail_sender(channel, line):
            raise RuntimeError("disconnected")

        SET_LOG_SENDER(fail_sender)
        game_output = FakeStream()
        wrapper = STD_OUT_WRAPPER(game_output, "stdout")

        wrapper.write("still visible\n")

        self.assertEqual(game_output.writes, ["[Python] still visible\n"])

    def test_sender_recursion_is_not_forwarded_again(self):
        game_output = FakeStream()
        wrapper = STD_OUT_WRAPPER(game_output, "stdout")

        def recursive_sender(channel, line):
            self.sent.append((channel, line))
            wrapper.write("sender diagnostic\n")
            return True

        SET_LOG_SENDER(recursive_sender)
        wrapper.write("outer\n")

        self.assertEqual(
            game_output.writes,
            ["[Python] outer\n", "[Python] sender diagnostic\n"],
        )
        self.assertEqual(self.sent, [("stdout", "[Python] outer")])

    def test_crlf_is_normalized_only_for_ipc_payload(self):
        game_output = FakeStream()
        wrapper = STD_OUT_WRAPPER(game_output, "stdout")

        wrapper.write("windows\r\n")

        self.assertEqual(game_output.writes, ["[Python] windows\n"])
        self.assertEqual(self.sent, [("stdout", "[Python] windows")])


if __name__ == "__main__":
    unittest.main()
