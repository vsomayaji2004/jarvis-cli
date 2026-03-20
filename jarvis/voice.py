"""Voice engine -- speech recognition and text-to-speech.

Handles microphone input via SpeechRecognition (Google free STT)
and audio output via Fish Audio TTS with the Jarvis voice model.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path


from jarvis import config as cfg


class VoiceEngine:
    """Manages speech-to-text and text-to-speech.

    Args:
        fish_api_key: Fish Audio API key for TTS.
        voice_model_id: Fish Audio voice model reference ID.
        speech_speed: TTS playback speed (0.5 - 2.0).
        language: Language code for speech recognition.
    """

    def __init__(
        self,
        fish_api_key: str = "",
        voice_model_id: str = "",
        speech_speed: float = 0.95,
        language: str = "en-US",
        listen_timeout: int = 10,
        phrase_time_limit: int = 60,
    ) -> None:
        self.fish_api_key = fish_api_key
        self.voice_model_id = voice_model_id or cfg.DEFAULTS["voice_model_id"]
        self.speech_speed = speech_speed
        self.language = language
        self.listen_timeout = listen_timeout
        self.phrase_time_limit = phrase_time_limit

        self._fish_client = None
        self._tts_config = None
        self._recognizer = None
        self._noise_calibrated = False
        self._temp_dir = Path(tempfile.mkdtemp(prefix="jarvis_"))

    @property
    def tts_available(self) -> bool:
        """Check whether TTS is configured."""
        return bool(self.fish_api_key)

    @property
    def stt_available(self) -> bool:
        """Check whether speech recognition is available."""
        try:
            import speech_recognition as sr  # noqa: F401
            return True
        except ImportError:
            return False

    def _init_fish(self) -> None:
        """Lazily initialize the Fish Audio client."""
        if self._fish_client is not None:
            return

        from fishaudio import FishAudio
        from fishaudio.types import TTSConfig, Prosody

        self._fish_client = FishAudio(api_key=self.fish_api_key)
        self._tts_config = TTSConfig(
            reference_id=self.voice_model_id,
            prosody=Prosody(speed=self.speech_speed),
            format="mp3",
        )

    def _play_audio_file(self, path: str) -> None:
        """Play an audio file using the best available system player."""
        import subprocess
        import platform

        if platform.system() == "Darwin":
            # macOS: afplay is built-in, no dependencies needed
            subprocess.run(["afplay", path], check=True, capture_output=True)
        else:
            # Linux/other: try ffplay, mpv, then aplay
            for player in [["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                          ["mpv", "--no-video", "--really-quiet", path],
                          ["aplay", path]]:
                try:
                    subprocess.run(player, check=True, capture_output=True)
                    return
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
            raise RuntimeError("No audio player found. Install ffmpeg or mpv.")

    def _init_recognizer(self):
        """Lazily initialize the speech recognizer."""
        if self._recognizer is not None:
            return self._recognizer

        import speech_recognition as sr

        self._recognizer = sr.Recognizer()
        self._recognizer.pause_threshold = 0.6  # 0.6s silence = phrase done
        self._recognizer.phrase_threshold = 0.15
        self._recognizer.non_speaking_duration = 0.3
        self._recognizer.dynamic_energy_threshold = True
        self._recognizer.energy_threshold = 300
        return self._recognizer

    def listen(self) -> str | None:
        """Listen for speech via the microphone and return transcribed text.

        Returns:
            Transcribed text, or None if nothing was understood.

        Raises:
            RuntimeError: If the microphone is not accessible.
        """
        import speech_recognition as sr

        recognizer = self._init_recognizer()

        try:
            with sr.Microphone() as source:
                if not self._noise_calibrated:
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    self._noise_calibrated = True
                audio = recognizer.listen(
                    source,
                    timeout=self.listen_timeout,
                    phrase_time_limit=self.phrase_time_limit,
                )
        except sr.WaitTimeoutError:
            return None
        except OSError as e:
            raise RuntimeError(
                f"Could not access the microphone: {e}. "
                "Check your audio input settings and permissions."
            ) from e

        try:
            text = recognizer.recognize_google(audio, language=self.language)
            return text.strip() if text else None
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            raise RuntimeError(
                f"Speech recognition service error: {e}. "
                "Check your internet connection."
            ) from e

    def generate_audio(self, text: str) -> str | None:
        """Generate TTS audio and save to temp file. Returns file path."""
        if not self.tts_available:
            return None

        self._init_fish()

        try:
            audio = self._fish_client.tts.convert(
                text=text,
                config=self._tts_config,
            )

            audio_path = self._temp_dir / "response.mp3"

            if isinstance(audio, bytes):
                audio_path.write_bytes(audio)
            else:
                collected = b"".join(
                    chunk if isinstance(chunk, bytes) else bytes([chunk])
                    for chunk in audio
                )
                audio_path.write_bytes(collected)

            return str(audio_path)
        except Exception as e:
            raise TTSError(f"Text-to-speech failed: {e}") from e

    def play_audio(self, path: str) -> None:
        """Play an audio file."""
        self._play_audio_file(path)

    def get_audio_duration(self, path: str) -> float:
        """Estimate audio duration from file size (MP3 ~128kbps)."""
        import os
        size = os.path.getsize(path)
        return size / 16000  # rough estimate for MP3

    def speak(self, text: str) -> None:
        """Generate and play TTS. For simple usage."""
        path = self.generate_audio(text)
        if path:
            self._play_audio_file(path)

    def stop_speaking(self) -> None:
        """Stop any currently playing audio."""
        pass  # Audio cleanup handled by system player subprocess

    def cleanup(self) -> None:
        """Release audio resources."""

    
        # Clean up temp files
        for f in self._temp_dir.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            self._temp_dir.rmdir()
        except OSError:
            pass


class TTSError(Exception):
    """Raised when text-to-speech conversion or playback fails."""
