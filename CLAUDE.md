# Jarvis CLI

## What This Is
A jarvis-style developer assistant with voice. Claude thinks, Jarvis speaks. Same Claude brain, same tools, same Max subscription -- with a calm, precise voice and system actions.

## API Keys Needed
- **Fish Audio API key** -- for Jarvis's voice (TTS). Get one at https://fish.audio/app/api-keys
- **NO Anthropic API key needed** -- this uses `claude -p` (Claude CLI) which runs on your Claude Max/Pro subscription. Zero API cost.

## First-Time Setup
1. **Check Claude CLI is installed**: Run `which claude`. If not found -> install from https://claude.ai/download
2. **Check Python**: Need Python 3.10+. Run `python3 --version`.
3. **Install portaudio** (needed for mic): `brew install portaudio`
4. **Install the package**: `pip install -e .`
5. **Set Fish Audio key**: `export FISH_API_KEY=your_key` or run `jarvis config fish_api_key YOUR_KEY`
6. **Test it**: Run `jarvis --text` first to verify Claude + TTS works without needing a mic
7. **Go voice**: Run `jarvis` for full voice mode

## How to Check if Already Set Up
- Run `jarvis config` -- shows current config. If `fish_api_key` is set -> ready to go
- Config file lives at `~/.jarvis/config.yaml`
- If `claude` CLI is not installed -> tell them to install Claude Code first
- **They do NOT need an Anthropic API key** -- `claude -p` uses their existing Claude subscription

## How It Works
```
Your voice -> SpeechRecognition (Google free STT) -> claude -p (Claude Max) -> Fish Audio TTS -> Jarvis voice
```

- `jarvis/cli.py` -- Main entry point, Click CLI
- `jarvis/voice.py` -- Mic capture (SpeechRecognition) + TTS (Fish Audio with Jarvis voice model)
- `jarvis/brain.py` -- Wraps `claude -p` subprocess, builds prompts with personality
- `jarvis/personality.py` -- The Jarvis persona prompt
- `jarvis/config.py` -- Manages `~/.jarvis/config.yaml`
- `jarvis/actions.py` -- Action system (built-ins + user-defined from ~/.jarvis/actions.yaml)
- `jarvis/ui.py` -- Rich terminal display with colored status indicators

## Key Details
- Voice model: Fish Audio `17e9990aa92c4da8b09ad3f0f2231e48` (Jarvis voice)
- Speech speed: 0.95x (configurable)
- Claude is called via `claude -p` with stdin, uses the user's Max subscription (zero API cost)
- Conversation history maintained in memory (last 10 exchanges)
- Phrase time limit: 30 seconds (configurable)
- Action system: whitelisted actions only, no arbitrary shell execution

## Action System
Claude can include ACTION blocks in responses:
```
ACTION: open_browser
ARGS: {"url": "https://google.com"}
SPEAK: yes
SAY: Opening Google for you.
```
Built-in actions: open_browser, open_terminal. Custom actions loaded from ~/.jarvis/actions.yaml

## Commands
- `jarvis` -- Full voice mode (speak + hear)
- `jarvis --text` -- Text only (type + hear)
- `jarvis --no-voice` -- Voice input, text output (speak + read)
- `jarvis config` -- Set Fish Audio API key
- `jarvis resume` -- Resume last conversation
