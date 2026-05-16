# ⬡ BLACK — AI Desktop Assistant

A fully AI-driven voice + text automation assistant with a floating UI.  
**Wake word:** `BLACK`  
**Powered by:** Claude (Anthropic) + Python

---

## ✨ Features

| Feature | Details |
|---|---|
| 🎤 Wake word | Say **"BLACK"** → BLACK replies *"Yes Sir, listening"* |
| 🤖 AI decisions | Claude AI decides every action — no hardcoded commands |
| 🖥 System control | Volume, shutdown, restart, sleep, lock screen |
| 🎵 App control | Open Spotify, Chrome, VLC, any app |
| 📷 Screen analysis | Say "analyze screen" → BLACK sees your screen and fixes errors |
| 💬 Text input | Type commands when mic isn't available |
| 🪟 Floating UI | Always-on-top draggable widget, works minimized |

---

## 🚀 Quick Start

### Step 1 — Install

```bash
# Clone / download this folder, then:
python3 setup.py
```

Or manually:

**Linux:**
```bash
sudo apt install portaudio19-dev python3-tk espeak -y
pip install anthropic SpeechRecognition pyttsx3 Pillow pyautogui psutil pyaudio --break-system-packages
```

**macOS:**
```bash
brew install portaudio
pip install anthropic SpeechRecognition pyttsx3 Pillow pyautogui psutil pyaudio
```

**Windows:**
```bash
pip install anthropic SpeechRecognition pyttsx3 Pillow pyautogui psutil
# PyAudio: download wheel from https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
```

### Step 2 — API Key

Get a free key at https://console.anthropic.com  
Either set it as an environment variable:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```
Or create a `.env` file in the BLACK folder:
```
ANTHROPIC_API_KEY=sk-ant-...
```
Or click the **🔑 API Key** button inside the app.

### Step 3 — Launch

```bash
# Linux/Mac:
python3 black.py
# or: ./launch.sh

# Windows:
python black.py
# or double-click: launch.bat
```

---

## 🗣 Example Commands

You can say **anything** — the AI figures it out:

| You say | What happens |
|---|---|
| `"BLACK"` | BLACK activates |
| `open spotify and play Blinding Lights` | Opens Spotify, starts playback |
| `volume up` | System volume increases |
| `set volume to 30` | Sets volume to 30% |
| `lock my screen` | Screen locks immediately |
| `analyze my screen` | Screenshots + AI describes + fixes errors |
| `open YouTube and search lo-fi music` | Opens browser, searches |
| `shut down in 10 seconds` | Initiates shutdown |
| `what time is it` | BLACK tells you |
| `open notepad and type hello world` | Opens Notepad, types text |

---

## 🏗 Architecture

```
BLACK
├── black.py          ← Main app (all-in-one)
│   ├── BlackUI       ← Floating Tkinter window
│   ├── BlackCore     ← Orchestrator / state machine
│   ├── AIBrain        ← Anthropic Claude API
│   ├── SystemController ← OS-level actions
│   ├── Speaker        ← pyttsx3 TTS
│   └── Listener       ← SpeechRecognition wake word
├── setup.py           ← One-time install helper
├── launch.sh          ← Linux/Mac launcher
├── launch.bat         ← Windows launcher
└── .env               ← API key (auto-created)
```

---

## ⚠️ Notes

- **Microphone**: If no mic is detected, text input still works fully.
- **Screen analysis**: Requires `Pillow`. The screen is captured, shrunk to 720p, and sent to Claude Vision.
- **Spotify control**: Opens the app. For deep Spotify control (specific songs), you can add the Spotify Web API key later.
- **Windows volume**: For smooth volume control, install [NirCmd](https://www.nirsoft.net/utils/nircmd.html) and add to PATH.

---

## 🔒 Privacy

- Voice is processed locally via Google Speech Recognition (requires internet).
- Screen captures are only sent to Anthropic API when you explicitly say "analyze screen".
- No data is stored or logged outside your machine.
