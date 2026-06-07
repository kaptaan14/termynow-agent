from __future__ import annotations

import asyncio
import errno
import os
import pty
import signal
import struct
import termios

import fcntl


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


class PtySession:
    """One interactive shell session bound to a cloud `session_id`."""

    def __init__(self, session_id: str, cols: int, rows: int, on_output) -> None:
        self.session_id = session_id
        self.on_output = on_output
        self._cols = cols
        self._rows = rows
        self._master_fd: int | None = None
        self._pid: int | None = None
        self._reader_task: asyncio.Task[None] | None = None

    def spawn(self) -> None:
        pid, master_fd = pty.fork()

        if pid == 0:
            try:
                os.chdir(os.path.expanduser("~"))

                # Proper terminal environment for clear, colors, TUIs, etc.
                os.environ["TERM"] = os.environ.get("TERM") or "xterm-256color"
                os.environ["COLORTERM"] = os.environ.get("COLORTERM") or "truecolor"

                # macOS default shell is usually zsh, Linux often bash.
                shell = os.environ.get("SHELL") or "/bin/bash"
                shell_name = os.path.basename(shell)

                # Interactive login shell: argv[0] starts with "-"
                os.execlp(shell, f"-{shell_name}")
            except OSError:
                os._exit(127)

        self._pid = pid
        self._master_fd = master_fd

        os.set_blocking(master_fd, False)
        _set_winsize(master_fd, self._rows, self._cols)

        self._reader_task = asyncio.create_task(self._pump())

    def resize(self, cols: int, rows: int) -> None:
        self._cols = cols
        self._rows = rows

        if self._master_fd is not None:
            _set_winsize(self._master_fd, rows, cols)

    async def _pump(self) -> None:
        assert self._master_fd is not None

        loop = asyncio.get_running_loop()
        master = self._master_fd

        while True:
            try:
                chunk = await loop.run_in_executor(
                    None,
                    lambda: os.read(master, 65536),
                )
            except BlockingIOError:
                await asyncio.sleep(0.01)
                continue
            except OSError as e:
                if e.errno in (errno.EIO, errno.EBADF):
                    chunk = b""
                else:
                    raise

            if not chunk:
                break

            await self.on_output(chunk)

    def write(self, data: bytes) -> None:
        if self._master_fd is None:
            return

        try:
            os.write(self._master_fd, data)
        except OSError:
            pass

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGHUP)
            except OSError:
                pass

        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass

        self._master_fd = None
        self._pid = None
        self._reader_task = None