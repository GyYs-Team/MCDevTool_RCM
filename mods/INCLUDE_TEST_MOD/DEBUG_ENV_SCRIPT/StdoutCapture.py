# -*- coding: utf-8 -*-
import threading


_LOG_SENDER = None
_SEND_STATE = threading.local()


def SET_LOG_SENDER(sender):
    global _LOG_SENDER
    _LOG_SENDER = sender


def _SEND_LOG(channel, line):
    sender = _LOG_SENDER
    if sender is None or getattr(_SEND_STATE, "active", False):
        return False
    _SEND_STATE.active = True
    try:
        return bool(sender(channel, line))
    except Exception:
        return False
    finally:
        _SEND_STATE.active = False


class STD_OUT_WRAPPER(object):
    def __init__(self, baseIO, channel):
        self.baseIO = baseIO
        self.channel = channel
        self.writeLock = threading.RLock()
        self._buffer = []

    def __getattr__(self, name):
        return getattr(self.baseIO, name)

    def _write_line(self, line, terminated=True):
        if terminated and line.endswith("\n"):
            line = line[:-1]
            if line.endswith("\r"):
                line = line[:-1]
        output = "[Python] " + line
        self.baseIO.write(output + ("\n" if terminated else ""))
        _SEND_LOG(self.channel, output)

    def write(self, data):
        with self.writeLock:
            parts = data.replace("\x00", "\\0").splitlines(True)
            for part in parts:
                if part.endswith("\n"):
                    line = "".join(self._buffer) + part
                    self._buffer = []
                    self._write_line(line)
                else:
                    self._buffer.append(part)

    def flush(self):
        with self.writeLock:
            if self._buffer:
                line = "".join(self._buffer)
                self._buffer = []
                self._write_line(line, False)
            flush = getattr(self.baseIO, "flush", None)
            if flush is not None:
                flush()

    def close(self):
        self.flush()
        return self.baseIO.close()

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def fileno(self):
        return self.baseIO.fileno()
