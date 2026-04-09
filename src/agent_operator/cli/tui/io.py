from __future__ import annotations

import select
import sys
import termios
import tty

from .controller import FleetWorkbenchController
from .models import TerminalSettings


def read_key(*, timeout_seconds: float) -> str | None:
    ready, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
    if not ready:
        return None
    first = sys.stdin.read(1)
    if first != "\x1b":
        return first
    ready, _, _ = select.select([sys.stdin], [], [], 0.01)
    if not ready:
        return first
    second = sys.stdin.read(1)
    if second != "[":
        return first + second
    ready, _, _ = select.select([sys.stdin], [], [], 0.01)
    if not ready:
        return first + second
    third = sys.stdin.read(1)
    return first + second + third


class raw_stdin:
    def __init__(self, file_descriptor: int) -> None:
        self._file_descriptor = file_descriptor
        self._original_settings: TerminalSettings | None = None

    def __enter__(self) -> raw_stdin:
        self._original_settings = termios.tcgetattr(self._file_descriptor)
        tty.setcbreak(self._file_descriptor)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._original_settings is not None:
            termios.tcsetattr(self._file_descriptor, termios.TCSADRAIN, self._original_settings)


async def run_fleet_workbench(*, controller: FleetWorkbenchController, poll_interval: float) -> None:
    from rich.console import Console
    from rich.live import Live

    console = Console()
    await controller.refresh()
    with raw_stdin(sys.stdin.fileno()), Live(controller.render(), console=console, refresh_per_second=8, screen=True) as live:
        while True:
            key = read_key(timeout_seconds=poll_interval)
            if key is None:
                await controller.refresh()
                live.update(controller.render(), refresh=True)
                continue
            keep_running = await controller.handle_key(key)
            live.update(controller.render(), refresh=True)
            if not keep_running:
                return
