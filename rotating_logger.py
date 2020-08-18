# Copyright (c) 2020 Leedehai. All rights reserved.
# Use of this source code is governed under the LICENSE.txt file.
# -----
# Adapted from my own work: https://gist.github.com/Leedehai/bf24f4de497ad1bd87055cb8709e322d

import json
import os
import socket
import socketserver
import sys
import tempfile
import time
import threading
from enum import IntEnum

# Unix domain socket
_SERVER_ADDR: str = os.path.join(tempfile.mkdtemp(prefix="score_"), "uds_sock")


def _remove_socket_file():
    os.remove(_SERVER_ADDR)
    os.rmdir(os.path.dirname(_SERVER_ADDR))


class _RotatingLogger:
    CURSOR_UP_AND_CLEAR = "\x1b[1A\x1b[2K"  # Cursor moves up and clears line.
    instance_ = None

    def __init__(self):
        self.arr_ = []  # Transient lines currently on screen.

    @staticmethod
    def get_instance():
        if _RotatingLogger.instance_ == None:
            _RotatingLogger.instance_ = _RotatingLogger()
        return _RotatingLogger.instance_

    def add_transient(self, s: str) -> None:
        original_qsize = len(self.arr_)
        if original_qsize == 5:  # Max count of transient lines.
            self.arr_.pop(0)
        self.arr_.append(s)
        sys.stderr.write(  # Cursor moves up and clears line.
            _RotatingLogger.CURSOR_UP_AND_CLEAR * original_qsize +
            "\x1b[?25l"  # Hide cursor.
            + ''.join(self.arr_) + "\x1b[?25h"  # Show cursor.
        )
        # Let the line stay for a while: prettier, though adding overhead
        time.sleep(0.05)

    def clear_transient_logs(self) -> None:
        for _ in range(len(self.arr_)):
            sys.stderr.write(_RotatingLogger.CURSOR_UP_AND_CLEAR)
        self.arr_.clear()

    def add_persistent(self, s: str) -> None:
        self.clear_transient_logs()
        sys.stderr.write(s)


class _Counter:
    instance_ = None

    def __init__(self):
        self.value_ = 0

    @staticmethod
    def get_instance():
        if _Counter.instance_ == None:
            _Counter.instance_ = _Counter()
        return _Counter.instance_

    def increment(self):
        self.value_ += 1
        return self

    def value(self) -> int:
        return self.value_


class LogAction(IntEnum):
    ADD_TRANSIENT = 1
    ADD_PERSISTENT = 2


class LogMessage:
    def __init__(self, form: LogAction, head: str, proper_text: str):
        self.form: LogAction = form
        self.head: str = head
        self.proper_text: str = proper_text

    @staticmethod
    def serialize(form: LogAction,
                  head: str = "",
                  proper_text: str = "") -> bytes:
        return json.dumps((form.value, head, proper_text),
                          separators=(',', ':')).encode()

    @staticmethod
    def deserialize(data_bytes: bytes):
        data = json.loads(data_bytes.decode(errors="backslashreplace"))
        return LogMessage(data[0], data[1], data[2])


class logging_server:
    def __init__(self):
        self.server_ = None

    def __enter__(self):
        self.server_ = _start_logging_server()

    def __exit__(self, exc_type, exc_value, traceback):
        if self.server_:
            _stop_server(self.server_)


def send_log(data: bytes) -> None:
    """
    Send a log message to the logging server. If the server wasn't
    created or already closed, throw error.
    """
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.connect(_SERVER_ADDR)
        sock.sendall(data)  # Better than send() to avoid partial write.


def clear_all_transient_logs():  # NOTE This is not thread safe.
    _RotatingLogger.get_instance().clear_transient_logs()


def _make_log_line(head: str, proper_text: str, count: int) -> str:
    return "%s %3s %s" % (head, count, proper_text)


class _UdpRequestHandler(socketserver.DatagramRequestHandler):
    def handle(self):
        # Unlike a TCP handler, here self.request is tuple (data, client socket)
        data_bytes, _ = self.request[0], self.request[1]
        message = LogMessage.deserialize(data_bytes)
        logline = _make_log_line(message.head, message.proper_text,
                                 _Counter.get_instance().increment().value())
        logger = _RotatingLogger.get_instance()
        if message.form == LogAction.ADD_TRANSIENT:
            logger.add_transient(logline)
            return
        if message.form == LogAction.ADD_PERSISTENT:
            logger.add_persistent(logline)
            return

    def finish(self):
        pass  # This is needed to not throw exception (Python 3.7.3, 3.8.2)


def _start_logging_server() -> socketserver.UnixDatagramServer:
    """
    Starts a logging server in another thread and returns the server instance.
    The socket is Unix domain socket (AF_UNIX), and the protocol is UDP
    (SOCK_DGRAM) because it is more important to avoid connection errors caused
    by TCP's backlog size limit than utilizing TCP's advantages over UDP.
    """
    if os.path.exists(_SERVER_ADDR):
        os.remove(_SERVER_ADDR)
    server = socketserver.UnixDatagramServer(_SERVER_ADDR, _UdpRequestHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    # Exits the server thread when the main thread exits.
    server_thread.daemon = True
    server_thread.start()
    return server


def _stop_server(server: socketserver.UnixDatagramServer) -> None:
    """
    Stops the server and waits until done.
    """
    # shutdown() tells server's serve_forever() loop to stop and waits until it
    # does. It must be called while the server is running in a different thread
    # (in the main thread here), otherwise it will deadlock.
    # https://docs.python.org/3/library/socketserver.html#socketserver.BaseServer.shutdown
    server.shutdown()
    server.server_close()
    _remove_socket_file()
