"""Action system for Jarvis.

Parses ACTION blocks from Claude's responses and executes
whitelisted system actions safely.

Actions are loaded from ~/.jarvis/actions.yaml. Users define their own
custom actions there. Two built-in actions (open_browser, open_terminal)
are always available.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

ACTIONS_FILE = Path.home() / ".jarvis" / "actions.yaml"


@dataclass
class ParsedAction:
    """A parsed action block from a response."""

    name: str
    args: dict
    speak: bool
    say: str

    @property
    def say_truncated(self) -> str:
        """SAY text capped at 150 characters."""
        if len(self.say) <= 150:
            return self.say
        return self.say[:147] + "..."


# ---------------------------------------------------------------------------
# Built-in actions (always available)
# ---------------------------------------------------------------------------

def _open_browser(args: dict) -> str:
    """Open a URL in the default browser (macOS)."""
    url = args.get("url", "")
    if not url:
        return "No URL provided."
    subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"Opened {url}"


def _open_terminal(args: dict) -> str:
    """Open a new Terminal window via osascript."""
    subprocess.Popen(
        ["osascript", "-e", 'tell application "Terminal" to do script ""'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return "Terminal opened."


BUILTIN_ACTIONS: dict[str, callable] = {
    "open_browser": _open_browser,
    "open_terminal": _open_terminal,
}


# ---------------------------------------------------------------------------
# User-defined actions from ~/.jarvis/actions.yaml
# ---------------------------------------------------------------------------

def _load_user_actions() -> dict:
    """Load custom actions from ~/.jarvis/actions.yaml.

    Each action is a dict with:
        command: str   -- shell command to run
        cwd: str       -- working directory (optional)
        description: str -- what it does (optional, shown in logs)

    Example actions.yaml:
        run_frontend:
          command: bun run dev
          cwd: ~/projects/my-app
          description: Start frontend dev server

        run_backend:
          command: source .env && uv run uvicorn main:app --reload
          cwd: ~/projects/my-api
          description: Start backend with env loaded
    """
    if not ACTIONS_FILE.exists():
        return {}

    try:
        data = yaml.safe_load(ACTIONS_FILE.read_text())
        if not isinstance(data, dict):
            return {}
        return data
    except (yaml.YAMLError, OSError) as e:
        log.warning("Failed to load %s: %s", ACTIONS_FILE, e)
        return {}


def _run_user_action(action_def: dict, args: dict) -> str:
    """Execute a user-defined shell action."""
    command = action_def.get("command", "")
    if not command:
        return "Action has no command defined."

    cwd = action_def.get("cwd", "")
    if cwd:
        cwd = str(Path(cwd).expanduser())

    description = action_def.get("description", command)

    subprocess.Popen(
        ["bash", "-c", command],
        cwd=cwd or None,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"{description}"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_ACTION_PATTERN = re.compile(
    r"ACTION:\s*(?P<name>\S+)\s*\n"
    r"ARGS:\s*(?P<args>.+)\s*\n"
    r"SPEAK:\s*(?P<speak>\S+)\s*\n"
    r"SAY:\s*(?P<say>.+)",
    re.IGNORECASE,
)


def parse_action(response: str) -> tuple[str, ParsedAction | None]:
    """Extract and remove an ACTION block from a response.

    Returns:
        (clean_response, parsed_action_or_none)
    """
    match = _ACTION_PATTERN.search(response)
    if not match:
        return response.strip(), None

    # Remove the action block from the displayed response
    clean = response[: match.start()].strip()

    name = match.group("name").strip()
    args_raw = match.group("args").strip()
    speak_raw = match.group("speak").strip().lower()
    say = match.group("say").strip()

    try:
        args = json.loads(args_raw)
    except json.JSONDecodeError:
        args = {}

    action = ParsedAction(
        name=name,
        args=args if isinstance(args, dict) else {},
        speak=speak_raw in ("yes", "true", "1"),
        say=say,
    )
    return clean, action


def execute(action: ParsedAction) -> str:
    """Execute a parsed action if it's in built-ins or user actions.

    Returns:
        Status message describing what happened.
    """
    # Check built-in actions first
    builtin = BUILTIN_ACTIONS.get(action.name)
    if builtin is not None:
        try:
            return builtin(action.args)
        except Exception as e:
            return f"Action '{action.name}' failed: {e}"

    # Check user-defined actions
    user_actions = _load_user_actions()
    user_action = user_actions.get(action.name)
    if user_action is not None:
        try:
            return _run_user_action(user_action, action.args)
        except Exception as e:
            return f"Action '{action.name}' failed: {e}"

    return f"Action '{action.name}' is not allowed."
