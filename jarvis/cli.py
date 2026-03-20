"""CLI entry point for Jarvis.

Provides the main `jarvis` command and the `jarvis config` subcommand.
"""

from __future__ import annotations

import queue as _queue
import sys
import time

import click
from rich.console import Console
from rich.live import Live

from jarvis import __version__
from jarvis import config as cfg
from jarvis.brain import Brain
from jarvis.ui import UI, Status
from jarvis.voice import VoiceEngine, TTSError
from jarvis.actions import parse_action, execute as execute_action


@click.group(invoke_without_command=True)
@click.option("--text", "-t", is_flag=True, help="Text-only mode (no microphone).")
@click.option("--no-voice", "-n", is_flag=True, help="Disable TTS output.")
@click.version_option(version=__version__, prog_name="jarvis")
@click.pass_context
def main(ctx: click.Context, text: bool, no_voice: bool) -> None:
    """Jarvis -- A developer assistant with voice. Powered by Claude."""
    if ctx.invoked_subcommand is not None:
        return

    _run_assistant(text_mode=text, no_voice=no_voice)


@main.command()
@click.argument("session_id", required=False)
def resume(session_id: str | None) -> None:
    """Resume a past conversation. Uses Claude's session history.

    Without arguments: continues the most recent Claude session.
    With a session ID: resumes that specific Claude session.
    """
    console = Console()
    settings = cfg.load()
    brain = Brain(max_history=settings["max_history"])

    if session_id:
        # Resume specific Claude session
        brain._resume_id = session_id
        console.print(f"  Resuming session {session_id}...", style="green")
    else:
        # Continue most recent Claude session
        brain._continue_mode = True
        console.print("  Continuing last session...", style="green")

    console.print()
    _run_assistant(text_mode=False, no_voice=False, brain=brain)


@main.command("config")
@click.argument("key", required=False)
@click.argument("value", required=False)
def config(key: str | None, value: str | None) -> None:
    """View or set configuration values.

    \b
    Examples:
        jarvis config                  # Show all config
        jarvis config fish_api_key     # Show one value
        jarvis config fish_api_key sk-xxx  # Set a value
    """
    console = Console()

    if key is None:
        # Show all config
        current = cfg.load()
        console.print("\n  [bold cyan]Jarvis Configuration[/bold cyan]")
        console.print(f"  [dim]Config file: {cfg.CONFIG_FILE}[/dim]\n")
        for k, v in current.items():
            display_value = _mask_secret(k, v)
            console.print(f"  [cyan]{k}[/cyan] = {display_value}")
        console.print()
        return

    if value is None:
        # Show one value
        current = cfg.load()
        if key in current:
            display_value = _mask_secret(key, current[key])
            console.print(f"  [cyan]{key}[/cyan] = {display_value}")
        else:
            console.print(f"  [red]Unknown key:[/red] {key}")
            console.print(f"  [dim]Available: {', '.join(cfg.DEFAULTS.keys())}[/dim]")
        return

    # Set value -- try to cast to the right type
    if key not in cfg.DEFAULTS:
        console.print(f"  [red]Unknown key:[/red] {key}")
        console.print(f"  [dim]Available: {', '.join(cfg.DEFAULTS.keys())}[/dim]")
        return

    default = cfg.DEFAULTS[key]
    if isinstance(default, int):
        value = int(value)
    elif isinstance(default, float):
        value = float(value)

    cfg.set_key(key, value)
    console.print(f"  [green]Set[/green] [cyan]{key}[/cyan] = {_mask_secret(key, value)}")


def _mask_secret(key: str, value) -> str:
    """Mask sensitive config values for display."""
    if "key" in key.lower() and isinstance(value, str) and len(value) > 8:
        return value[:4] + "..." + value[-4:]
    return str(value)


def _run_assistant(text_mode: bool = False, no_voice: bool = False, brain: Brain | None = None) -> None:
    """Main conversation loop."""
    ui = UI()
    settings = cfg.load()

    # --- Validate prerequisites ---
    if brain is None:
        brain = Brain(max_history=settings["max_history"])
    if not brain.available:
        ui.show_error(
            "The 'claude' CLI is not installed or not on your PATH.\n"
            "         Install it: https://docs.anthropic.com/en/docs/claude-cli"
        )
        sys.exit(1)

    # --- Initialize voice engine ---
    voice = VoiceEngine(
        fish_api_key=settings["fish_api_key"] if not no_voice else "",
        voice_model_id=settings["voice_model_id"],
        speech_speed=settings["speech_speed"],
        language=settings["language"],
        listen_timeout=settings["listen_timeout"],
        phrase_time_limit=settings["phrase_time_limit"],
    )

    # Warn about missing config
    if not text_mode and not voice.stt_available:
        ui.show_error(
            "SpeechRecognition or PyAudio not installed. "
            "Falling back to text mode.\n"
            "         Install: pip install SpeechRecognition PyAudio"
        )
        text_mode = True

    if not no_voice and not voice.tts_available:
        ui.show_info(
            "No Fish Audio API key configured. Running without voice output.\n"
            "         Set it: jarvis config fish_api_key YOUR_KEY"
        )

    # Wire up activity callback so we can see what Claude is doing
    brain._activity_callback = lambda msg: ui.show_info(f"  {msg}")

    # Show models in use
    ui.show_info("Brain: Opus (thinking) → Haiku (voice summary) → Fish Audio (TTS)")

    # --- Start ---
    ui.show_welcome()

    try:
        _conversation_loop(ui, brain, voice, text_mode)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        voice.cleanup()
        ui.show_goodbye()


def _conversation_loop(
    ui: UI,
    brain: Brain,
    voice: VoiceEngine,
    text_mode: bool,
) -> None:
    """Run the listen-think-speak loop until interrupted."""
    while True:
        # --- 1. Get user input ---
        if text_mode:
            try:
                user_input = ui.console.input("  [bold cyan]You:[/bold cyan] ").strip()
            except EOFError:
                break
            if not user_input:
                continue
        else:
            ui.show_status(Status.LISTENING)
            try:
                user_input = voice.listen()
            except KeyboardInterrupt:
                break
            except RuntimeError as e:
                ui.clear_status()
                ui.show_error(str(e))
                ui.show_info("Switching to text mode.")
                text_mode = True
                continue

            ui.clear_status()

            if user_input is None:
                continue  # Silence or unrecognized -- keep listening

            ui.show_user(user_input)

        # --- Natural language commands ---
        cmd = user_input.strip().lower()

        # Exit - only exact short commands or full phrases (not partial word matches)
        if cmd in ("exit", "quit", "bye", "goodbye", "stop", "/exit", "/q"):
            break
        exit_phrases = [
            "gotta go", "got to go", "i'm out", "i'm done", "wrap up",
            "talk later", "see you later", "see ya", "good night",
            "signing off", "peace out", "catch you later", "bye jarvis",
            "bye bye", "that's all", "we're done", "jarvis exit",
            "jarvis quit", "jarvis bye",
        ]
        if any(cmd == phrase for phrase in exit_phrases):
            break

        # Clear conversation
        if any(phrase in cmd for phrase in [
            "forget everything", "start over", "clear the conversation",
            "fresh start", "new conversation", "reset",
        ]) or cmd in ("/clear", "/c"):
            brain.history.clear()
            brain._first_sent = False
            brain._save_history()
            ui.show_info("Conversation cleared.")
            continue

        # --- 2. Think (streaming with animated orb) ---
        try:
            proc, chunks, done = brain.think_stream(user_input)
        except RuntimeError as e:
            ui.show_error(str(e))
            continue

        response_text = ""
        start_time = time.time()
        try:
            with Live(
                ui.render_stream_frame("", True),
                console=ui.console,
                refresh_per_second=20,
                transient=True,
            ) as live:
                while not done.is_set() or not chunks.empty():
                    if time.time() - start_time > 300:
                        proc.kill()
                        raise TimeoutError("Claude took too long to respond.")

                    # Drain all available chunks
                    try:
                        while True:
                            response_text += chunks.get_nowait()
                    except _queue.Empty:
                        pass

                    live.update(ui.render_stream_frame(
                        response_text, is_streaming=not done.is_set(),
                    ))
                    time.sleep(0.04)

            proc.wait(timeout=10)
            if proc.returncode != 0:
                error = proc.stderr.read().strip() or "Unknown error from claude CLI"
                raise RuntimeError(f"Claude CLI error: {error}")

            response = brain.finalize_stream(response_text.strip())

        except (RuntimeError, TimeoutError) as e:
            ui.show_error(str(e))
            continue

        # --- 3. Parse action block (if any) ---
        clean_response, action = parse_action(response)

        # --- 4. Display + speak response ---
        if action:
            result = execute_action(action)
            ui.show_info(f" {result}")

        speak_text = None
        if action and action.speak and action.say:
            speak_text = action.say_truncated
        elif not action and clean_response:
            speak_text = clean_response

        display_text = clean_response or speak_text or ""

        if speak_text and voice.tts_available and not text_mode:
            try:
                import threading

                audio_path = voice.generate_audio(speak_text)
                if audio_path:
                    duration = voice.get_audio_duration(audio_path)
                    # Start audio and text reveal at the same time
                    player = threading.Thread(target=voice.play_audio, args=(audio_path,), daemon=True)
                    player.start()
                    ui.show_jarvis_streaming(display_text, duration)
                    player.join()
                else:
                    ui.show_jarvis(display_text)
            except TTSError as e:
                ui.show_jarvis(display_text)
                ui.show_info(f"Voice output failed: {e}")
        elif display_text:
            ui.show_jarvis(display_text)


if __name__ == "__main__":
    main()
