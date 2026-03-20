"""Claude integration via the claude CLI.

Wraps `claude -p` (headless mode) to send prompts and receive responses.
Uses Claude Max through the CLI -- zero API cost.
"""

from __future__ import annotations

import queue as _queue
import shutil
import subprocess
import threading
from pathlib import Path
from dataclasses import dataclass, field

from jarvis.personality import get_system_prompt


@dataclass
class Message:
    """A single conversation turn."""

    role: str  # "user" or "jarvis"
    content: str


class Brain:
    """Manages conversation with Claude via the CLI.

    Maintains a rolling history window and constructs prompts
    with the Jarvis personality baked in.
    """

    def __init__(self, max_history: int = 10) -> None:
        self.max_history = max_history
        self.history: list[Message] = []
        self._claude_path = shutil.which("claude")
        self._activity_callback = None
        self._first_sent = False
        self._sessions_dir = Path.home() / ".jarvis" / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._current_session_id: str | None = None
        self._history_file = Path.home() / ".jarvis" / "history.json"  # legacy
        self._continue_mode = False  # When True, pass --continue to claude
        self._resume_id: str | None = None  # When set, pass --resume ID to claude
        # Start a new session by default
        self._new_session()

    @property
    def available(self) -> bool:
        """Check whether the claude CLI is installed and on PATH."""
        return self._claude_path is not None

    def think(self, user_input: str) -> str:
        """Send user input to Claude and return the response.

        Args:
            user_input: What the user said or typed.

        Returns:
            Claude's response text.

        Raises:
            RuntimeError: If the claude CLI is not installed.
            TimeoutError: If Claude takes longer than 120 seconds.
        """
        if not self.available:
            raise RuntimeError(
                "The 'claude' CLI was not found on your PATH. "
                "Install it from https://docs.anthropic.com/en/docs/claude-cli"
            )

        self.history.append(Message(role="user", content=user_input))

        prompt = self._build_prompt()

        try:
            cmd = [
                self._claude_path,
                "-p",
                "--output-format", "text",
                "--dangerously-skip-permissions",
                # Uses default model (Opus) for full intelligence
            ]
            if self._continue_mode:
                cmd.append("--continue")
                self._continue_mode = False
            elif self._resume_id:
                cmd.extend(["--resume", self._resume_id])
                self._resume_id = None

            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300,
            )

        except subprocess.TimeoutExpired:
            raise TimeoutError("Claude took too long to respond. Try again.")

        if result.returncode != 0:
            error = result.stderr.strip() or "Unknown error from claude CLI"
            raise RuntimeError(f"Claude CLI error: {error}")

        full_response = result.stdout.strip()
        if not full_response:
            full_response = "Hmm, I lost my train of thought for a second. What were you saying?"

        # If response is long, use Haiku to create a short spoken summary
        # Short responses get spoken as-is
        if len(full_response) > 300:
            try:
                summary_result = subprocess.run(
                    [self._claude_path, "-p", "--output-format", "text",
                     "--model", "claude-haiku-4-5-20251001"],
                    input=(
                        "Summarize this in 2-3 natural spoken sentences. "
                        "No formatting, no markdown, no bullet points. "
                        "Just talk naturally like you're telling someone what happened:\n\n"
                        + full_response
                    ),
                    capture_output=True, text=True, timeout=15,
                )
                spoken = summary_result.stdout.strip()
                if spoken:
                    response = spoken
                else:
                    response = full_response
            except (subprocess.TimeoutExpired, Exception):
                response = full_response
        else:
            response = full_response

        # Clean any formatting that slipped through
        response = response.replace("**", "").replace("```", "").replace("##", "").replace("# ", "").strip()

        self.history.append(Message(role="jarvis", content=response))
        self._full_response = full_response  # Keep full response for display
        self._trim_history()
        self._save_history()

        return response

    def think_stream(self, user_input: str):
        """Start a streaming Claude call.

        Returns (proc, chunks_queue, done_event).
        Reads stdout character-by-character in a background thread.
        Call finalize_stream(full_text) after iteration completes.
        """
        if not self.available:
            raise RuntimeError(
                "The 'claude' CLI was not found on your PATH. "
                "Install it from https://docs.anthropic.com/en/docs/claude-cli"
            )

        self.history.append(Message(role="user", content=user_input))
        prompt = self._build_prompt()

        cmd = [
            self._claude_path,
            "-p",
            "--output-format", "text",
            "--dangerously-skip-permissions",
        ]
        if self._continue_mode:
            cmd.append("--continue")
            self._continue_mode = False
        elif self._resume_id:
            cmd.extend(["--resume", self._resume_id])
            self._resume_id = None

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        proc.stdin.write(prompt)
        proc.stdin.close()

        chunks: _queue.Queue[str] = _queue.Queue()
        done = threading.Event()

        def _reader() -> None:
            try:
                while True:
                    c = proc.stdout.read(1)
                    if not c:
                        break
                    chunks.put(c)
            finally:
                done.set()

        threading.Thread(target=_reader, daemon=True).start()
        return proc, chunks, done

    def finalize_stream(self, full_response: str) -> str:
        """Finalize after streaming completes.

        Handles Haiku summary for long responses, updates history,
        and returns the spoken text.
        """
        if not full_response:
            full_response = "Hmm, I lost my train of thought for a second. What were you saying?"

        self._full_response = full_response

        if len(full_response) > 300:
            try:
                summary_result = subprocess.run(
                    [self._claude_path, "-p", "--output-format", "text",
                     "--model", "claude-haiku-4-5-20251001"],
                    input=(
                        "Summarize this in 2-3 natural spoken sentences. "
                        "No formatting, no markdown, no bullet points. "
                        "Just talk naturally like you're telling someone what happened:\n\n"
                        + full_response
                    ),
                    capture_output=True, text=True, timeout=15,
                )
                spoken = summary_result.stdout.strip()
                if not spoken:
                    spoken = full_response
            except (subprocess.TimeoutExpired, Exception):
                spoken = full_response
        else:
            spoken = full_response

        spoken = spoken.replace("**", "").replace("```", "").replace("##", "").replace("# ", "").strip()

        self.history.append(Message(role="jarvis", content=spoken))
        self._trim_history()
        self._save_history()

        return spoken

    def _build_prompt(self) -> str:
        """Construct the prompt. Always includes personality since each call is a new subprocess."""
        # Always include personality - each claude -p call is stateless
        parts = [
            get_system_prompt(),
            "",
        ]

        # Include recent conversation history for context
        recent = self.history[-6:]  # Last 3 exchanges
        if len(recent) > 1:
            parts.append("Recent conversation:")
            for msg in recent[:-1]:  # All except the current message
                speaker = "User" if msg.role == "user" else "Jarvis"
                parts.append(f"{speaker}: {msg.content}")
            parts.append("")

        parts.append(f"User: {self.history[-1].content}")
        parts.append("")
        parts.append("Respond as Jarvis. 2-3 sentences max, natural speech, NO markdown, NO formatting, NO code blocks, NO bullet points. Just talk naturally.")

        return "\n".join(parts)

    def _new_session(self) -> None:
        """Start a fresh session."""
        import time
        self._current_session_id = time.strftime("%Y%m%d-%H%M%S")
        self.history = []
        self._first_sent = False

    def load_session(self, session_id: str) -> bool:
        """Load a specific session by ID."""
        import json as _json
        session_file = self._sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return False
        try:
            data = _json.loads(session_file.read_text())
            self.history = [Message(role=m["role"], content=m["content"]) for m in data.get("messages", [])]
            self._current_session_id = session_id
            self._first_sent = bool(self.history)
            return True
        except (KeyError, _json.JSONDecodeError, OSError):
            return False

    def list_sessions(self) -> list[dict]:
        """List all saved sessions with preview info."""
        import json as _json
        sessions = []
        for f in sorted(self._sessions_dir.glob("*.json"), reverse=True):
            try:
                data = _json.loads(f.read_text())
                messages = data.get("messages", [])
                preview = ""
                for m in messages:
                    if m["role"] == "user":
                        preview = m["content"][:60]
                        break
                sessions.append({
                    "id": f.stem,
                    "date": data.get("date", f.stem),
                    "messages": len(messages),
                    "preview": preview,
                })
            except (KeyError, _json.JSONDecodeError, OSError):
                continue
        return sessions

    def _save_history(self) -> None:
        """Persist current session to disk."""
        import json as _json
        import time
        if not self.history:
            return
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        session_file = self._sessions_dir / f"{self._current_session_id}.json"
        data = {
            "date": time.strftime("%Y-%m-%d %H:%M"),
            "messages": [{"role": m.role, "content": m.content} for m in self.history],
        }
        session_file.write_text(_json.dumps(data, indent=2))

    def _load_history(self) -> None:
        """Legacy - not used anymore."""
        pass

    def _trim_history(self) -> None:
        """Keep only the most recent exchanges."""
        max_messages = self.max_history * 2  # Each exchange is 2 messages
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

    def reset(self) -> None:
        """Clear conversation history."""
        self.history.clear()
