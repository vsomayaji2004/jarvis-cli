"""Rich-powered terminal UI for Jarvis.

Provides a clean, minimal display with status indicators
and a scrolling conversation transcript.
"""

from __future__ import annotations

from enum import Enum

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.text import Text


class Status(Enum):
    """Visual states for the UI."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


# Status display configuration
_STATUS_STYLES: dict[Status, tuple[str, str, str]] = {
    #                    (dot_color,  label,          style)
    Status.IDLE:       ("dim",       "Ready",        "dim"),
    Status.LISTENING:  ("green",     "Listening...",  "bold green"),
    Status.THINKING:   ("yellow",    "Thinking...",   "bold yellow"),
    Status.SPEAKING:   ("blue",      "Speaking...",   "bold blue"),
    Status.ERROR:      ("red",       "Error",         "bold red"),
}


class UI:
    """Terminal interface for Jarvis.

    Uses Rich for colored output and status indicators.
    Keeps things simple -- prints sequentially rather than
    using Live display, which plays better with audio I/O.
    """

    def __init__(self) -> None:
        self.console = Console()

    def show_welcome(self) -> None:
        """Display the startup banner."""
        title = Text()
        title.append("Jarvis", style="bold cyan")

        subtitle = Text("Developer assistant. Powered by Claude.", style="dim italic")

        welcome = Text()
        welcome.append("\n")
        welcome.append("  Say something, and I'll respond.\n", style="dim")
        welcome.append("  Press ", style="dim")
        welcome.append("Ctrl+C", style="bold dim")
        welcome.append(" to exit.\n", style="dim")

        panel = Panel(
            welcome,
            title=title,
            subtitle=subtitle,
            border_style="cyan",
            padding=(0, 2),
        )
        self.console.print()
        self.console.print(panel)
        self.console.print()

    def show_status(self, status: Status) -> None:
        """Print a status indicator line."""
        dot_color, label, style = _STATUS_STYLES[status]
        indicator = Text()
        indicator.append("  ● ", style=dot_color)
        indicator.append(label, style=style)
        self.console.print(indicator)

    def show_user(self, text: str) -> None:
        """Display what the user said."""
        line = Text()
        line.append("  You: ", style="bold cyan")
        line.append(text)
        self.console.print(line)

    def show_jarvis(self, text: str) -> None:
        """Display Jarvis's response all at once."""
        line = Text()
        line.append("  jarvis: ", style="bold cyan")
        line.append(text)
        self.console.print(line)
        self.console.print()

    def show_jarvis_streaming(self, text: str, duration: float = 3.0) -> None:
        """Reveal Jarvis's response word by word, timed to audio duration."""
        import time

        words = text.split()
        if not words:
            return

        ms_per_word = max(0.06, duration / len(words))
        revealed = "  jarvis: "

        for i, word in enumerate(words):
            revealed += word + " "
            # Clear line and reprint
            self.console.print(f"\r{revealed}", end="", highlight=False, style="magenta" if i == 0 else None)
            time.sleep(ms_per_word)

        self.console.print()  # Final newline
        self.console.print()  # Breathing room

    def show_error(self, message: str) -> None:
        """Display an error message."""
        line = Text()
        line.append("  Error: ", style="bold red")
        line.append(message, style="red")
        self.console.print(line)
        self.console.print()

    def show_info(self, message: str) -> None:
        """Display an informational message."""
        self.console.print(f"  [dim]{message}[/dim]")

    def show_goodbye(self) -> None:
        """Display the exit message."""
        self.console.print()
        self.console.print("  [dim cyan]Until next time, sir.[/dim cyan]")
        self.console.print()

    def render_stream_frame(self, response_text: str = "", is_streaming: bool = True) -> Group:
        """Build a Rich renderable for the streaming Jarvis display.

        Shows a centered spinner (orb) while streaming, with response text below.
        """
        parts: list = []

        # Top divider
        parts.append(Rule("Jarvis", style="dim cyan"))
        parts.append(Text(""))

        # Orb (spinner)
        if is_streaming:
            label = " thinking..." if not response_text else ""
            parts.append(Align.center(Spinner("dots", text=label, style="cyan")))
            parts.append(Text(""))

        # Response text
        if response_text:
            resp = Text()
            resp.append("> ", style="dim cyan")
            resp.append(response_text)
            parts.append(resp)

        return Group(*parts)

    def clear_status(self) -> None:
        """Move cursor up to overwrite the last status line."""
        # Move up one line and clear it
        self.console.print("\033[A\033[2K", end="")
