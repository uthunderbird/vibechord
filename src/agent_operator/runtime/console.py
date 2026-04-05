from rich.console import Console as RichConsole


class RichConsoleAdapter:
    def __init__(self) -> None:
        self._console = RichConsole()

    def print(self, message: str) -> None:
        self._console.print(message)
