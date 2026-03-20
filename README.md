# Jarvis CLI

A voice-controlled developer assistant that runs in your terminal. It uses Claude as the brain and Fish Audio for text-to-speech, so you can talk to your computer and have it write code, run commands, edit files, and search the web -- hands-free.

Inspired by J.A.R.V.I.S. from *Iron Man* (2008).

---

## How it works

Jarvis connects four things together:

1. **Google Speech Recognition** (free) converts your voice to text
2. **Claude Opus** via `claude -p` processes your request with full tool access
3. **Claude Haiku** summarizes long responses into 2-3 spoken sentences
4. **Fish Audio TTS** speaks the response back to you in a custom voice

While Claude is thinking, a streaming UI shows an animated orb and displays the response in real-time as tokens arrive. When the response is long, the full output is shown in your terminal and a short summary is spoken aloud.

Claude runs through the CLI in headless mode (`claude -p`), which means it uses your existing Claude Max or Pro subscription. There's no separate API key or per-token billing for the AI. The only external cost is Fish Audio for voice output.

All conversation history is stored locally on your machine at `~/.jarvis/sessions/`. Nothing is uploaded anywhere.

---

## Prerequisites

Before installing, you need:

- **Python 3.10 or higher** -- check with `python3 --version`
- **Claude CLI** -- installed and signed in. Check with `which claude`. If not installed, get it at [claude.ai/download](https://claude.ai/download)
- **Claude Max or Pro subscription** -- required for `claude -p` to work
- **Fish Audio API key** -- for voice output. Get one at [fish.audio/app/api-keys](https://fish.audio/app/api-keys)
- **portaudio** -- system library required for microphone input

---

## Installation

```bash
# 1. Make sure you have Python 3.10+
python3 --version

# 2. Install Claude CLI (if you don't have it already)
#    Download from https://claude.ai/download
#    Then sign in with: claude login

# 3. Install portaudio (required for microphone access)
brew install portaudio          # macOS
# sudo apt install portaudio19-dev  # Linux

# 4. Clone and install
git clone https://github.com/vsomayaji2004/jarvis-cli.git
cd jarvis-cli
pip install -e .

# 5. Set your Fish Audio API key
#    Create an account at https://fish.audio
#    Get your API key at https://fish.audio/app/api-keys
#    Add credit at https://fish.audio/app/billing (required for TTS to work)
jarvis config fish_api_key YOUR_KEY_HERE

# 6. Test in text mode first (no mic needed)
jarvis --text

# 7. Run with full voice
jarvis
```

---

## Commands

### Starting Jarvis

| Command | Input | Output |
|---|---|---|
| `jarvis` | Voice (microphone) | Voice (speakers) |
| `jarvis --text` or `jarvis -t` | Text (keyboard) | Voice (speakers) |
| `jarvis --no-voice` or `jarvis -n` | Voice (microphone) | Text (terminal) |
| `jarvis --text --no-voice` | Text (keyboard) | Text (terminal) |

### Other commands

| Command | What it does |
|---|---|
| `jarvis resume` | Continue your most recent Claude session |
| `jarvis resume SESSION_ID` | Resume a specific session |
| `jarvis config` | Show all current settings |
| `jarvis config KEY` | Show a single setting |
| `jarvis config KEY VALUE` | Update a setting |
| `jarvis --version` | Show version number |

### Voice commands during a session

- Say **"goodbye"**, **"I'm done"**, **"see ya"**, or similar to end the session
- Say **"start over"**, **"forget everything"**, or **"reset"** to clear history
- Press **Ctrl+C** to exit immediately

---

## Configuration

All settings are stored in `~/.jarvis/config.yaml`. You can edit the file directly or use `jarvis config`.

| Setting | Default | Description |
|---|---|---|
| `fish_api_key` | (empty) | Your Fish Audio API key. Required for voice output. |
| `voice_model_id` | `17e9990aa92c4da8b09ad3f0f2231e48` | Fish Audio voice model ID. Change this to use a different voice. |
| `speech_speed` | `0.95` | Voice speed. Range: 0.5 (slow) to 2.0 (fast). |
| `language` | `en-US` | Language for speech recognition. |
| `max_history` | `10` | Number of conversation exchanges to remember. |
| `listen_timeout` | `10` | Seconds to wait for you to start speaking. |
| `phrase_time_limit` | `30` | Maximum seconds for a single spoken phrase. |

The Fish Audio API key can also be set via the `FISH_API_KEY` environment variable, which takes priority over the config file.

### Changing the voice

The default voice is a J.A.R.V.I.S.-style model. To use a different voice:

1. Browse voices at [fish.audio](https://fish.audio)
2. Click a voice you like -- the model ID is in the URL (e.g. `fish.audio/m/MODEL_ID`)
3. Set it:

```bash
jarvis config voice_model_id NEW_MODEL_ID
```

---

## Custom actions

Jarvis can trigger system actions like opening URLs, starting dev servers, or launching terminals. Two actions are built in: `open_browser` and `open_terminal`.

You can define your own actions in `~/.jarvis/actions.yaml`. These are personal to your machine and never committed to the repo.

```yaml
# ~/.jarvis/actions.yaml

run_frontend:
  command: npm run dev
  cwd: ~/projects/my-app
  description: Start frontend dev server

run_backend:
  command: source .env && python -m uvicorn main:app --reload
  cwd: ~/projects/my-api
  description: Start backend with env loaded
```

Each action needs a `command` (shell command to run). `cwd` (working directory, supports `~`) and `description` (shown in terminal output) are optional.

Claude learns about your custom actions automatically and will use them when you ask it to start, open, or run things. See `actions.example.yaml` in the repo for more examples.

---

## Project structure

```
jarvis/
  cli.py           Entry point and main conversation loop
  brain.py          Claude integration via subprocess (claude -p)
  voice.py          Microphone input (Google STT) and audio output (Fish Audio TTS)
  ui.py             Terminal display with Rich (streaming orb, status indicators)
  personality.py    System prompt that defines how Claude responds as Jarvis
  actions.py        Action parser and executor (built-in + user-defined)
  config.py         Config file management (~/.jarvis/config.yaml)
```

---

## Security

Jarvis runs Claude with `--dangerously-skip-permissions` so it can create files, edit code, and run terminal commands when you ask. This is the same level of access as running Claude Code normally, but triggered by voice.

Things to be aware of:

- Run Jarvis in project directories where you're comfortable with Claude making changes
- Voice recognition can mishear commands -- be careful around important files
- Conversation history is stored locally at `~/.jarvis/sessions/` and never leaves your machine
- Custom actions in `~/.jarvis/actions.yaml` run shell commands -- only add actions you trust

---

## Credits

- Inspired by J.A.R.V.I.S. from *Iron Man* (2008), directed by Jon Favreau
- Built with [Claude](https://claude.ai) by Anthropic
- Voice powered by [Fish Audio](https://fish.audio)
- Terminal UI by [Rich](https://github.com/Textualize/rich)

## License

MIT. See [LICENSE](LICENSE).
