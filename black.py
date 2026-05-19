"""
BLACK - AI Desktop Assistant  v3.0
Wake word : "BLACK"
Vision AI : Gemini 2.5 Flash sees your screen and controls everything
"""

import threading, time, os, subprocess, platform, json, base64
import tkinter as tk, datetime, io, sys

# Hand mouse (optional)
try:
    from hand_mouse import HandMouse, HandMouseUI
    HAND_OK = True
except ImportError:
    HAND_OK = False

# Hand mouse (optional)
try:
    from hand_mouse import HandMouse, HandMouseUI
    HAND_OK = True
except ImportError:
    HAND_OK = False

# ── optional deps ──────────────────────────────────────────────────────────────
try:
    import speech_recognition as sr
    SR_OK = True
except ImportError:
    SR_OK = False

try:
    import pyttsx3
    TTS_OK = True
except ImportError:
    TTS_OK = False

try:
    from PIL import ImageGrab, Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.05   # small pause between actions
    GUI_OK = True
except ImportError:
    GUI_OK = False

# DO NOT set DPI awareness — let pyautogui use its own logical pixel space
# Setting DPI awareness breaks pyautogui coordinate mapping on scaled displays

try:
    import pyperclip
    CLIP_OK = True
except ImportError:
    CLIP_OK = False

try:
    import google.generativeai as genai
    GEMINI_OK = True
except ImportError:
    GEMINI_OK = False

# ── config ─────────────────────────────────────────────────────────────────────
WAKE_WORD      = "black"
# Load API key - check env, then .env file
def _load_api_key():
    # 1. Environment variable
    key = os.environ.get("GEMINI_API_KEY","")
    if key: return key
    # 2. .env file next to black.py
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=",1)[1].strip().strip('"').strip("'")
    return ""

def _save_api_key(key: str):
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = [l for l in f.readlines() if not l.startswith("GEMINI_API_KEY=")]
        lines.append(f"GEMINI_API_KEY={key}\n")
        with open(env_path,"w") as f:
            f.writelines(lines)
        print(f"[KEY] Saved to {env_path}")
    except Exception as e:
        print(f"[KEY] Save error: {e}")

GEMINI_API_KEY = _load_api_key()
# Pre-set key if none found
if not GEMINI_API_KEY:
    GEMINI_API_KEY = "AIzaSyAHgyQLAWUNbwS5aC6AELmC7u0TDalcg6k"
    _save_api_key(GEMINI_API_KEY)
OS_NAME        = platform.system()          # Windows / Darwin / Linux

# ══════════════════════════════════════════════════════════════════════════════
#  SCREEN CAPTURE
# ══════════════════════════════════════════════════════════════════════════════
# Real screen dimensions (set on first capture)
_REAL_W = 0
_REAL_H = 0
_CAPT_W = 1280
_CAPT_H = 720

# Screen dimensions — set on startup
_PYAG_W  = 0   # pyautogui logical width  (what we click on)
_PYAG_H  = 0   # pyautogui logical height
_CAPT_W  = 1280
_CAPT_H  = 720

def _init_screen_dims():
    """Get pyautogui screen size (logical pixels) — used for all click scaling."""
    global _PYAG_W, _PYAG_H
    if GUI_OK:
        _PYAG_W, _PYAG_H = pyautogui.size()
    else:
        # Fallback: try ctypes logical size (no DPI awareness set)
        try:
            import ctypes
            _PYAG_W = ctypes.windll.user32.GetSystemMetrics(0)
            _PYAG_H = ctypes.windll.user32.GetSystemMetrics(1)
        except Exception:
            _PYAG_W, _PYAG_H = 1920, 1080
    print(f"[SCREEN] pyautogui logical size = {_PYAG_W}x{_PYAG_H}")

_init_screen_dims()

def draw_grid(img):
    """Overlay a labelled coordinate grid on the screenshot.
       Grid every 64px on 1280x720 → AI reads exact coords from labels.
    """
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(img, "RGBA")
    W, H  = img.size
    STEP  = 64
    GCOL  = (0,   200, 255, 100)   # cyan grid lines
    LCOL  = (255, 255,   0, 230)   # yellow labels
    CCOL  = (255,  50,  50, 200)   # red crosshair

    # grid lines
    for x in range(0, W+1, STEP):
        draw.line([(x,0),(x,H)], fill=GCOL, width=1)
    for y in range(0, H+1, STEP):
        draw.line([(0,y),(W,y)], fill=GCOL, width=1)

    # labels + crosshairs
    try:    font = ImageFont.truetype("arial.ttf", 8)
    except: font = ImageFont.load_default()

    for gy in range(0, H, STEP):
        for gx in range(0, W, STEP):
            cx = gx + STEP//2
            cy = gy + STEP//2
            # top-left label of each cell
            draw.text((gx+2, gy+2), f"{gx},{gy}", fill=LCOL, font=font)
            # red crosshair at cell centre
            draw.line([(cx-6,cy),(cx+6,cy)], fill=CCOL, width=1)
            draw.line([(cx,cy-6),(cx,cy+6)], fill=CCOL, width=1)

    # bottom ruler
    for x in range(0, W+1, STEP):
        draw.text((x+1, H-11), str(x), fill=LCOL, font=font)
    # right ruler
    for y in range(0, H+1, STEP):
        draw.text((W-28, y+1), str(y), fill=LCOL, font=font)

    return img


def grab_screen() -> str | None:
    """Capture screen → resize to 1280x720 → add coordinate grid → send to AI."""
    global _CAPT_W, _CAPT_H
    if not PIL_OK:
        return None
    try:
        # Try mss first (faster, more accurate)
        try:
            import mss
            with mss.mss() as sct:
                mon = sct.monitors[1]
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        except ImportError:
            img = ImageGrab.grab(all_screens=False)
            if GUI_OK:
                pw, ph = pyautogui.size()
                if img.size != (pw, ph):
                    img = img.resize((pw, ph), Image.LANCZOS)

        # Resize to fixed 1280x720
        _CAPT_W, _CAPT_H = 1280, 720
        img = img.resize((_CAPT_W, _CAPT_H), Image.LANCZOS)

        # Draw coordinate grid so AI can pinpoint exact locations
        img = draw_grid(img)

        buf = io.BytesIO()
        img.save(buf, "PNG")
        print(f"[SCREEN] {_PYAG_W}x{_PYAG_H} pyag → 1280x720 AI + grid overlay")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[SCREEN] {e}")
        return None
def scale_coords(x, y):
    """Map AI image coords (1280x720) → pyautogui logical screen coords."""
    global _PYAG_W, _PYAG_H, _CAPT_W, _CAPT_H
    if _PYAG_W == 0:
        _init_screen_dims()
    rx = int(x * _PYAG_W / _CAPT_W)
    ry = int(y * _PYAG_H / _CAPT_H)
    rx = max(0, min(rx, _PYAG_W - 1))
    ry = max(0, min(ry, _PYAG_H - 1))
    print(f"[COORDS] AI({x},{y}) → pyag({rx},{ry})  [{_PYAG_W}x{_PYAG_H}]")
    return rx, ry

# ══════════════════════════════════════════════════════════════════════════════
#  SYSTEM CONTROLLER
# ══════════════════════════════════════════════════════════════════════════════
class SysCtrl:
    @staticmethod
    def _run(cmd, shell=False):
        try:
            r = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=15)
            return r.stdout.strip() or r.stderr.strip() or "ok"
        except Exception as e:
            return f"err:{e}"

    # power
    def shutdown(self):
        if OS_NAME=="Windows": return self._run("shutdown /s /t 5",shell=True)
        if OS_NAME=="Darwin":  return self._run(["osascript","-e",'tell app "System Events" to shut down'])
        return self._run("systemctl poweroff",shell=True)

    def restart(self):
        if OS_NAME=="Windows": return self._run("shutdown /r /t 5",shell=True)
        if OS_NAME=="Darwin":  return self._run(["osascript","-e",'tell app "System Events" to restart'])
        return self._run("systemctl reboot",shell=True)

    def lock(self):
        if OS_NAME=="Windows": return self._run("rundll32.exe user32.dll,LockWorkStation",shell=True)
        if OS_NAME=="Darwin":  return self._run(["osascript","-e",'tell application "System Events" to keystroke "q" using {command down, control down}'])
        return self._run("xdg-screensaver lock",shell=True)

    def sleep(self):
        if OS_NAME=="Windows": return self._run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0",shell=True)
        if OS_NAME=="Darwin":  return self._run(["pmset","sleepnow"])
        return self._run("systemctl suspend",shell=True)

    # volume
    def vol_up(self, step=10):
        if OS_NAME=="Windows":
            if GUI_OK:
                for _ in range(step//2): pyautogui.press("volumeup")
                return "vol up"
        if OS_NAME=="Darwin": return self._run(["osascript","-e",f"set volume output volume (output volume of (get volume settings)+{step})"])
        return self._run(f"amixer -D pulse sset Master {step}%+",shell=True)

    def vol_down(self, step=10):
        if OS_NAME=="Windows":
            if GUI_OK:
                for _ in range(step//2): pyautogui.press("volumedown")
                return "vol down"
        if OS_NAME=="Darwin": return self._run(["osascript","-e",f"set volume output volume (output volume of (get volume settings)-{step})"])
        return self._run(f"amixer -D pulse sset Master {step}%-",shell=True)

    def mute(self):
        if OS_NAME=="Windows" and GUI_OK: pyautogui.press("volumemute"); return "muted"
        if OS_NAME=="Darwin": return self._run(["osascript","-e","set volume with output muted"])
        return self._run("amixer -D pulse sset Master toggle",shell=True)

    def set_vol(self, lvl):
        if OS_NAME=="Darwin": return self._run(["osascript","-e",f"set volume output volume {lvl}"])
        if OS_NAME=="Linux": return self._run(f"amixer -D pulse sset Master {lvl}%",shell=True)
        return f"set vol {lvl}"

    # apps / browser
    def open_app(self, name, wait=3.5):
        w={"spotify":"spotify.exe","chrome":"chrome.exe","notepad":"notepad.exe",
           "calculator":"calc.exe","explorer":"explorer.exe","firefox":"firefox.exe",
           "vlc":"vlc.exe","word":"winword.exe","excel":"excel.exe","paint":"mspaint.exe",
           "cmd":"cmd.exe","whatsapp":"WhatsApp.exe","telegram":"Telegram.exe",
           "discord":"Discord.exe","vscode":"code.exe","vs code":"code.exe","edge":"msedge.exe"}
        m={"spotify":"Spotify","chrome":"Google Chrome","safari":"Safari","finder":"Finder",
           "terminal":"Terminal","whatsapp":"WhatsApp","telegram":"Telegram"}
        lx={"spotify":"spotify","chrome":"google-chrome","firefox":"firefox","vlc":"vlc",
            "terminal":"x-terminal-emulator","whatsapp":"whatsapp-desktop"}
        n = name.lower().strip()
        if OS_NAME=="Windows":
            exe = w.get(n, name)
            self._run(f'start "" "{exe}"',shell=True)
        elif OS_NAME=="Darwin":
            self._run(["open","-a",m.get(n,name)])
        else:
            self._run(f"{lx.get(n,name)} &",shell=True)
        time.sleep(wait)
        return f"opened {name}"

    def open_url(self, url):
        import webbrowser; webbrowser.open(url); time.sleep(2.5); return f"opened {url}"

    # mouse
    def click(self, x=None, y=None):
        if not GUI_OK: return "no pyautogui"
        if x is not None and y is not None:
            rx, ry = scale_coords(x, y)
            pyautogui.moveTo(rx, ry, duration=0.2)
            time.sleep(0.05)
            pyautogui.click(rx, ry)
        else:
            pyautogui.click()
        time.sleep(0.25); return f"click scaled→({x},{y})"

    def dbl_click(self, x=None, y=None):
        if not GUI_OK: return "no pyautogui"
        if x is not None and y is not None:
            rx, ry = scale_coords(x, y)
            pyautogui.moveTo(rx, ry, duration=0.2)
            time.sleep(0.05)
            pyautogui.doubleClick(rx, ry)
        else:
            pyautogui.doubleClick()
        time.sleep(0.25); return "dbl click"

    def right_click(self, x=None, y=None):
        if not GUI_OK: return "no pyautogui"
        if x is not None and y is not None:
            rx, ry = scale_coords(x, y)
            pyautogui.moveTo(rx, ry, duration=0.2)
            time.sleep(0.05)
            pyautogui.rightClick(rx, ry)
        else:
            pyautogui.rightClick()
        return "right click"

    def scroll(self, direction="down", amount=3):
        if not GUI_OK: return "no pyautogui"
        pyautogui.scroll(amount if direction=="up" else -amount)
        return f"scroll {direction}"

    def move_mouse(self, x, y):
        if not GUI_OK: return "no pyautogui"
        rx, ry = scale_coords(x, y)
        pyautogui.moveTo(rx, ry, duration=0.3)
        return f"moved to real({rx},{ry})"

    # keyboard
    def type_text(self, text):
        if not GUI_OK: return "no pyautogui"
        time.sleep(0.3)
        if CLIP_OK:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl","v")
        else:
            pyautogui.typewrite(str(text), interval=0.04)
        return f"typed:{text}"

    def press_key(self, key):
        if not GUI_OK: return "no pyautogui"
        pyautogui.press(key); return f"press {key}"

    def hotkey(self, *keys):
        if not GUI_OK: return "no pyautogui"
        pyautogui.hotkey(*keys); return f"hotkey {keys}"

    # media
    def play_pause(self):
        if GUI_OK: pyautogui.press("playpause"); return "play/pause"
    def next_track(self):
        if GUI_OK: pyautogui.press("nexttrack"); return "next"
    def prev_track(self):
        if GUI_OK: pyautogui.press("prevtrack"); return "prev"

    def search_web(self, q):
        return self.open_url(f"https://www.google.com/search?q={q.replace(' ','+')}")

    def sys_info(self):
        info={"os":OS_NAME,"time":datetime.datetime.now().strftime("%H:%M %d-%m-%Y")}
        try:
            import psutil
            info["cpu"]=f"{psutil.cpu_percent(0.3):.0f}%"
            info["ram"]=f"{psutil.virtual_memory().percent:.0f}%"
            b=psutil.sensors_battery()
            if b: info["battery"]=f"{b.percent:.0f}% {'⚡' if b.power_plugged else '🔋'}"
        except: pass
        return info

# ══════════════════════════════════════════════════════════════════════════════
#  AI BRAIN  — Vision Loop
# ══════════════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are BLACK, a powerful AI desktop assistant with FULL vision and full control of the user's computer.
You can SEE the screen in real-time and perform any action. Always call the user "Sir".

━━━ RESPONSE FORMAT ━━━
Reply ONLY with a valid JSON object — no markdown, no explanation outside JSON:
{
  "speech": "<what to say>",
  "actions": [{"type": "<action>", "params": {}}],
  "need_screen": false
}

Set "need_screen": true when you need to see the screen AGAIN after executing actions
(e.g. to find a button, verify a result, or continue a multi-step task).

━━━ ALL AVAILABLE ACTIONS ━━━

SYSTEM:
  open_app        {"app": "whatsapp", "wait": 4}
  open_url        {"url": "https://..."}
  shutdown        {}
  restart         {}
  lock            {}
  sleep           {}
  sys_info        {}

VOLUME:
  vol_up          {"step": 10}
  vol_down        {"step": 10}
  set_vol         {"level": 50}
  mute            {}

━━━ HOW TO USE THE COORDINATE GRID ━━━
Every screenshot you receive has a CYAN GRID overlaid with:
  • YELLOW labels (e.g. "128,64") at the top-left of every 64×64 cell
  • RED CROSSHAIR at the centre of every cell  
  • RULER numbers along the bottom (X) and right edge (Y)

To click something:
  1. Find the element in the screenshot
  2. Read the nearest yellow grid label → that gives the cell's top-left (gx, gy)
  3. Estimate how many pixels right/down the element centre is inside that cell
  4. Final coordinate = (gx + offset_x,  gy + offset_y)
  Example: button centre is in cell "768,384", about 20px right and 10px down
           → use x=788, y=394
Always click the exact CENTRE of buttons and input fields.

MOUSE (coordinates on the 1280×720 grid image — auto-scaled to your real screen):
  click           {"x": 640, "y": 360}
  dbl_click       {"x": 640, "y": 360}
  right_click     {"x": 640, "y": 360}
  scroll          {"direction": "down", "amount": 3}
  move_mouse      {"x": 640, "y": 360}

KEYBOARD:
  type_text       {"text": "hello world"}
  press_key       {"key": "enter"}
  hotkey          {"keys": ["ctrl", "a"]}

MEDIA:
  play_pause      {}
  next_track      {}
  prev_track      {}

FLOW:
  wait            {"seconds": 2}
  grab_screen     {}    ← triggers another screenshot, use with need_screen:true
  say_only        {}

━━━ VISION AUTOMATION RULES ━━━
1. ALWAYS wait after open_app (minimum 3-4 seconds) before any click or type.
2. Use "need_screen": true whenever you need to SEE the current state before deciding next action.
3. For EVERY multi-step task (send message, click button, fill form etc):
   - Open app / page → wait → set need_screen:true
   - You receive the screenshot → identify the EXACT CENTER pixel of target element → click
   - Verify result → continue
4. COORDINATE ACCURACY: Be very precise. Look carefully at the screenshot.
   Click the CENTER of input fields, buttons, and links.
   If you miss, use need_screen:true to check and try again.

EXAMPLE — "open whatsapp and send hi to Sharan":
  Step1: [{open_app:whatsapp, wait:5}],  need_screen:true
  Step2: (sees screen) → [{click: search_bar_coords}, {type_text:"Sharan"}, {wait:1}], need_screen:true
  Step3: (sees results) → [{click: sharan_contact_coords}, {wait:1}], need_screen:true
  Step4: (sees chat) → [{click: message_input_coords}, {type_text:"hi"}, {press_key:"enter"}]

4. Never say "I cannot do that" — always attempt using vision + control.
5. Do NOT add "Task completed, Sir." in speech — it is added automatically.
"""

class Brain:
    def __init__(self, key=""):
        self.api_key = key
        self.history = []

    def think(self, prompt: str, screen_b64: str | None = None) -> dict:
        if not self.api_key:
            return {"speech":"No API key set, Sir. Click 🔑 to add it.", "actions":[], "need_screen":False}
        if not GEMINI_OK:
            return {"speech":"google-generativeai not installed.", "actions":[], "need_screen":False}
        try:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-2.5-flash",
                                          system_instruction=SYSTEM_PROMPT)
            parts = []
            if screen_b64:
                img = Image.open(io.BytesIO(base64.b64decode(screen_b64)))
                parts.append(img)
            parts.append(prompt)

            chat = model.start_chat(history=self.history[-20:])
            resp = chat.send_message(parts)
            raw  = resp.text.strip().replace("```json","").replace("```","").strip()

            result = json.loads(raw)
            self.history += [{"role":"user","parts":[prompt]},
                              {"role":"model","parts":[raw]}]
            return result
        except json.JSONDecodeError:
            return {"speech":"Understood, Sir.","actions":[],"need_screen":False}
        except Exception as e:
            print(f"[AI] {e}")
            return {"speech":f"Error: {str(e)[:100]}","actions":[],"need_screen":False}

# ══════════════════════════════════════════════════════════════════════════════
#  TEXT-TO-SPEECH  — fixed: fresh engine per utterance, non-blocking
# ══════════════════════════════════════════════════════════════════════════════
class Speaker:
    """
    TTS Speaker — uses Windows SAPI COM directly via win32com (most reliable)
    or falls back to subprocess powershell, then pyttsx3.
    Each utterance gets a FRESH COM object — no state corruption between speaks.
    """
    def __init__(self):
        self._q    = []
        self._lock = threading.Lock()
        self._speaking = False
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _speak_windows(self, text: str) -> bool:
        """Speak using Windows SAPI via PowerShell subprocess — totally stateless."""
        try:
            # Escape single quotes in text
            safe = text.replace("'", " ").replace('"', ' ')
            cmd = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Rate = 1; "
                f"$s.Volume = 100; "
                f"$s.Speak('{safe}'); "
                f"$s.Dispose()"
            )
            result = subprocess.run(
                ["powershell", "-NonInteractive", "-Command", cmd],
                timeout=60,
                capture_output=True
            )
            return result.returncode == 0
        except Exception as e:
            print(f"[TTS-PS] {e}")
            return False

    def _speak_pyttsx3(self, text: str) -> bool:
        """Fallback: pyttsx3 with fresh init each call."""
        if not TTS_OK:
            return False
        try:
            eng = pyttsx3.init()
            eng.setProperty("rate", 158)
            eng.setProperty("volume", 1.0)
            eng.say(text)
            eng.runAndWait()
            try: eng.stop()
            except: pass
            return True
        except Exception as e:
            print(f"[TTS-py] {e}")
            return False

    def _run(self):
        while True:
            if self._q:
                with self._lock:
                    text = self._q.pop(0)
                self._speaking = True
                print(f"[BLACK]: {text}")
                if OS_NAME == "Windows":
                    ok = self._speak_windows(text)
                    if not ok:
                        self._speak_pyttsx3(text)
                else:
                    self._speak_pyttsx3(text)
                self._speaking = False
            else:
                time.sleep(0.05)

    def say(self, text: str):
        if not text or not text.strip():
            return
        with self._lock:
            if not self._q or self._q[-1] != text:
                self._q.append(text)

    def clear(self):
        with self._lock:
            self._q.clear()

# ══════════════════════════════════════════════════════════════════════════════
#  MICROPHONE  — fixed energy threshold + continuous loop
# ══════════════════════════════════════════════════════════════════════════════
class Mic:
    def __init__(self):
        self.ok = SR_OK
        if SR_OK:
            self.rec = sr.Recognizer()
            self.rec.energy_threshold         = 50    # very sensitive
            self.rec.dynamic_energy_threshold  = False # don't auto-adjust up
            self.rec.dynamic_energy_adjustment_damping = 0.15
            self.rec.pause_threshold           = 0.5  # faster response
            self.rec.phrase_threshold          = 0.1  # catch short phrases
            self.rec.non_speaking_duration     = 0.3
        else:
            self.rec = None

    def calibrate(self):
        if not self.ok: return
        try:
            with sr.Microphone() as src:
                print("[MIC] calibrating ambient noise...")
                self.rec.adjust_for_ambient_noise(src, duration=1.0)
                # Cap threshold low so mic stays sensitive
                self.rec.energy_threshold = min(self.rec.energy_threshold, 80)
                self.rec.dynamic_energy_threshold = False
                print(f"[MIC] Ready. threshold={self.rec.energy_threshold:.0f}")
        except OSError as e:
            print(f"[MIC] No audio device found: {e}")
            self.ok = False
        except Exception as e:
            print(f"[MIC] calibrate failed: {e}")
            self.ok = False

    def listen(self, timeout=4, limit=12) -> str | None:
        if not self.ok: return None
        try:
            with sr.Microphone() as src:
                # Boost mic input level before recording
                src.CHUNK = 512
                audio = self.rec.listen(src, timeout=timeout,
                                        phrase_time_limit=limit)
            # Try Google with boosted audio data
            raw = audio.get_raw_data()
            import audioop
            # Amplify audio by 3x for better recognition
            try:
                raw = audioop.mul(raw, audio.sample_width, 3)
            except Exception:
                pass
            import speech_recognition as _sr
            boosted = _sr.AudioData(raw, audio.sample_rate, audio.sample_width)
            text = self.rec.recognize_google(boosted, language="en-IN")
            print(f"[MIC] '{text}'")
            return text.lower()
        except sr.WaitTimeoutError: return None
        except sr.UnknownValueError: return None
        except Exception as e:
            print(f"[MIC] {e}"); return None

# ══════════════════════════════════════════════════════════════════════════════
#  CORE ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════
class BlackCore:
    def __init__(self, notify=None):
        self.ctrl    = SysCtrl()
        self.speaker = Speaker()
        self.mic     = Mic()
        self.brain   = Brain(GEMINI_API_KEY)
        self.notify  = notify or (lambda *a: None)
        self.active  = False
        self.running = True
        self._busy   = False   # guard: only one listen at a time

    def set_key(self, key):
        global GEMINI_API_KEY
        GEMINI_API_KEY = key
        self.brain.api_key = key
        _save_api_key(key)

    # ── process one command through full vision loop ───────────────────────
    def process(self, text: str):
        self.notify("status","thinking")
        self.notify("user_text", text)

        # auto-grab screen if user mentions it
        screen = None
        if any(w in text.lower() for w in ["screen","analyze","analyse","fix error","what's on","what do you see","see my"]):
            screen = grab_screen()

        result = self.brain.think(text, screen)
        self._handle(result)
        self.notify("status","listening" if self.active else "idle")

    def _handle(self, result: dict, depth=0):
        if depth > 8: return   # prevent infinite vision loops

        speech      = result.get("speech","")
        actions     = result.get("actions",[])
        need_screen = result.get("need_screen", False)

        if speech:
            self.notify("ai_text", speech)
            self.notify("status","speaking")
            self.speaker.say(speech)

        SKIP = {"say_only","get_system_info","sys_info","grab_screen"}
        real = [a for a in actions if a.get("type","") not in SKIP]

        for a in actions:
            self._exec(a.get("type",""), a.get("params",{}))

        # vision loop — AI asked to see screen again
        if need_screen:
            time.sleep(0.6)
            self.notify("status","thinking")
            self.notify("action","👁 checking screen...")
            screen = grab_screen()
            if screen:
                followup = self.brain.think(
                    "Here is the current screen. Continue the task, Sir.", screen)
                self._handle(followup, depth+1)
                return   # completion spoken inside recursion

        if real:
            time.sleep(0.3)
            self.speaker.say("Task completed, Sir.")
            self.notify("ai_text","Task completed, Sir.")

    def _exec(self, t: str, p: dict):
        self.notify("action", t)
        try:
            if   t=="open_app":    self.ctrl.open_app(p.get("app",""), p.get("wait", p.get("seconds",3.5)))
            elif t=="open_url":    self.ctrl.open_url(p.get("url",""))
            elif t=="shutdown":    self.ctrl.shutdown()
            elif t=="restart":     self.ctrl.restart()
            elif t=="lock":        self.ctrl.lock()
            elif t=="sleep":       self.ctrl.sleep()
            elif t=="vol_up":      self.ctrl.vol_up(p.get("step",10))
            elif t=="vol_down":    self.ctrl.vol_down(p.get("step",10))
            elif t=="set_vol":     self.ctrl.set_vol(p.get("level",50))
            elif t=="mute":        self.ctrl.mute()
            elif t=="click":       self.ctrl.click(p.get("x"), p.get("y"))
            elif t=="dbl_click":   self.ctrl.dbl_click(p.get("x"), p.get("y"))
            elif t=="right_click": self.ctrl.right_click(p.get("x"), p.get("y"))
            elif t=="scroll":      self.ctrl.scroll(p.get("direction","down"), p.get("amount",3))
            elif t=="move_mouse":  self.ctrl.move_mouse(p.get("x",0), p.get("y",0))
            elif t=="type_text":   self.ctrl.type_text(p.get("text",""))
            elif t=="press_key":   self.ctrl.press_key(p.get("key",""))
            elif t=="hotkey":      self.ctrl.hotkey(*p.get("keys",[]))
            elif t=="play_pause":  self.ctrl.play_pause()
            elif t=="next_track":  self.ctrl.next_track()
            elif t=="prev_track":  self.ctrl.prev_track()
            elif t=="search_web":  self.ctrl.search_web(p.get("query",""))
            elif t=="sys_info":
                info = self.ctrl.sys_info()
                self.notify("ai_text", str(info))
            elif t=="wait":
                s = float(p.get("seconds", p.get("ms",1)))
                if s > 100: s /= 1000
                time.sleep(s)
            elif t in ("grab_screen","say_only","screen_analysis"):
                pass   # handled by need_screen flag
            else:
                print(f"[EXEC] unknown action: {t}")
        except Exception as e:
            print(f"[EXEC] {t} error: {e}")

    # ── wake word loop ─────────────────────────────────────────────────────
    def _wake_loop(self):
        if not self.mic.ok:
            self.notify("status","no_mic")
            return   # stop immediately — don't loop if no mic
        self.notify("status","waiting_wake_word")
        while self.running:
            if self._busy: 
                time.sleep(0.2)
                continue
            heard = self.mic.listen(timeout=4, limit=6)
            if heard and (WAKE_WORD in heard or "blank" in heard or "block" in heard):
                self.active = True
                self.notify("status","activated")
                self.speaker.say("Yes Sir, listening.")
                self.notify("ai_text","Yes Sir, listening.")
                self._get_command()
            time.sleep(0.05)

    def _get_command(self):
        self._busy = True
        self.notify("status","listening")
        cmd = self.mic.listen(timeout=9, limit=20)
        if cmd:
            threading.Thread(target=self.process, args=(cmd,), daemon=True).start()
        else:
            self.speaker.say("I didn't catch that, Sir.")
            self.notify("ai_text","I didn't catch that, Sir.")
            self.notify("status","waiting_wake_word")
        self.active = False
        self._busy = False

    def start(self):
        def _init():
            # Boost system volume to max on Windows
            if OS_NAME == "Windows":
                try:
                    import subprocess
                    # Set volume to 100% using PowerShell
                    subprocess.run(
                        ["powershell","-c",
                         "(New-Object -ComObject WScript.Shell).SendKeys([char]174*2);"
                         "Add-Type -TypeDefinition '"
                         "using System.Runtime.InteropServices;"
                         "public class Vol {"
                         "[DllImport(\"user32.dll\")]"
                         "public static extern void keybd_event(byte b,byte s,int f,int e);"
                         "}'; "
                         "for($i=0;$i-lt50;$i++){[Vol]::keybd_event(0xAF,0,1,0);Start-Sleep -Milliseconds 20}"],
                        capture_output=True, timeout=5
                    )
                except Exception as e:
                    print(f"[VOL] {e}")
                # Also try nircmd
                try:
                    subprocess.run(["nircmd.exe","setsysvolume","65535"],
                                   capture_output=True, timeout=3)
                except Exception:
                    pass
                # Boost mic input level via PowerShell
                try:
                    subprocess.run(
                        ["powershell","-c",
                         "$obj=Get-WmiObject Win32_SoundDevice;"
                         "Write-Host $obj.Name"],
                        capture_output=True, timeout=3
                    )
                except Exception:
                    pass

            if self.mic.ok:
                self.mic.calibrate()
                if self.mic.ok:
                    threading.Thread(target=self._wake_loop, daemon=True).start()
                    return
            # Mic not available
            self.notify("status","no_mic")
            self.notify("ai_text",
                "Microphone not detected, Sir. "
                "Install PyAudio (py -3.11 -m pip install pyaudio) "
                "or use the text box / 🎤 button below.")
        threading.Thread(target=_init, daemon=True).start()

    def send(self, text):
        threading.Thread(target=self.process, args=(text,), daemon=True).start()

    def manual_listen(self):
        """One-shot listen triggered by mic button."""
        if self._busy:
            return   # already listening
        def _go():
            self._busy = True
            if not self.mic.ok:
                self.speaker.say("Microphone not available, Sir.")
                self.notify("ai_text","Microphone not available, Sir.")
                self._busy = False
                return
            self.notify("status","listening")
            self.notify("ai_text","Listening, Sir...")
            cmd = self.mic.listen(timeout=9, limit=20)
            if cmd:
                self.process(cmd)
            else:
                self.speaker.say("Didn't catch that, Sir.")
                self.notify("ai_text","Didn't catch that, Sir.")
                self.notify("status","idle")
            self._busy = False
        threading.Thread(target=_go, daemon=True).start()

# ══════════════════════════════════════════════════════════════════════════════
#  FLOATING UI
# ══════════════════════════════════════════════════════════════════════════════
class BlackUI:
    BG="#080c18"; AC="#00d4ff"; AC2="#7b2fff"
    TX="#ddeeff"; DM="#2a3a5a"; GR="#00ff99"; RD="#ff3355"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BLACK")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)
        sw=self.root.winfo_screenwidth(); sh=self.root.winfo_screenheight()
        self.root.geometry(f"430x540+{sw-450}+{sh-580}")
        self.root.configure(bg=self.BG)
        self._drag={}; self._orb_state="idle"; self._pulse=0
        self._build()
        self.core = BlackCore(notify=self._event)
        self.core.start()
        self._tick()

    # ── UI build ──────────────────────────────────────────────────────────
    def _build(self):
        # title bar
        bar=tk.Frame(self.root,bg="#04060f",height=40,cursor="fleur")
        bar.pack(fill="x"); bar.pack_propagate(False)
        bar.bind("<Button-1>",self._ds); bar.bind("<B1-Motion>",self._dm)

        lbl=tk.Label(bar,text="⬡  B L A C K",bg="#04060f",fg=self.AC,
                     font=("Courier New",13,"bold"))
        lbl.pack(side="left",padx=12,pady=9)
        lbl.bind("<Button-1>",self._ds); lbl.bind("<B1-Motion>",self._dm)

        # mic indicator
        self.mic_dot=tk.Label(bar,
            text="● MIC ON" if SR_OK else "● NO MIC",
            bg="#04060f",
            fg=self.GR if SR_OK else self.RD,
            font=("Courier New",7))
        self.mic_dot.pack(side="right",padx=6)

        bf=tk.Frame(bar,bg="#04060f"); bf.pack(side="right",padx=4)
        tk.Button(bf,text="—",bg="#04060f",fg=self.DM,bd=0,
                  font=("Courier New",12),command=self._min,
                  activebackground="#04060f",activeforeground=self.AC,
                  cursor="hand2").pack(side="left")
        tk.Button(bf,text="✕",bg="#04060f",fg=self.DM,bd=0,
                  font=("Courier New",12),command=self.root.destroy,
                  activebackground="#04060f",activeforeground=self.RD,
                  cursor="hand2").pack(side="left",padx=(4,0))

        # orb
        of=tk.Frame(self.root,bg=self.BG); of.pack(pady=(4,0))
        self.orb=tk.Canvas(of,width=80,height=80,bg=self.BG,highlightthickness=0)
        self.orb.pack()
        self._draw_orb("idle")
        self.slbl=tk.Label(self.root,text='Say  " BLACK "  to wake',
                           bg=self.BG,fg=self.DM,font=("Courier New",8))
        self.slbl.pack(pady=(1,0))

        # ── input row (packed BEFORE chat so it's always visible) ──
        ir=tk.Frame(self.root,bg="#0d1426",pady=6); ir.pack(fill="x",padx=10,pady=(4,2))
        self.ent=tk.Entry(ir,bg="#1a2a44",fg="#ffffff",insertbackground=self.AC,
                          font=("Courier New",11),bd=0,highlightthickness=2,
                          highlightcolor=self.AC,highlightbackground=self.AC,
                          relief="flat")
        self.ent.pack(side="left",fill="x",expand=True,ipady=9,padx=(6,6))
        self.ent.bind("<Return>",self._send)
        self.ent.insert(0,"Type a command...")
        self.ent.config(fg="#4a7aaa")
        self.ent.bind("<FocusIn>",  self._entry_focus_in)
        self.ent.bind("<FocusOut>", self._entry_focus_out)

        self.mbtn=tk.Button(ir,text="🎤",bg=self.AC2,fg="white",bd=0,
                            font=("Courier New",11),padx=10,pady=4,
                            command=self._mic_click,
                            activebackground=self.GR,cursor="hand2")
        self.mbtn.pack(side="left",padx=(0,4))

        tk.Button(ir,text="▶",bg=self.AC,fg="#000000",bd=0,
                  font=("Courier New",11,"bold"),padx=12,pady=4,
                  command=self._send,
                  activebackground="#00aadd",cursor="hand2").pack(side="left")

        # ── util row ──
        ur=tk.Frame(self.root,bg=self.BG); ur.pack(fill="x",padx=10,pady=(0,4))
        for txt,cmd in [("📷 Screen",self._screen),
                        ("🔑 API Key",self._apikey),
                        ("🗑 Clear",self._clear),
                        ("ℹ Sys Info",self._sysinfo)]:
            tk.Button(ur,text=txt,bg="#0d1426",fg=self.TX,bd=0,
                      font=("Courier New",8),padx=6,pady=3,
                      command=cmd,activebackground=self.DM,
                      cursor="hand2").pack(side="left",padx=2)

        # Hand mouse button
        self._hand_btn = tk.Button(ur, text="🖐 Hand",
                      bg="#0d1426", fg=self.TX, bd=0,
                      font=("Courier New",8), padx=6, pady=3,
                      command=self._open_hand_mouse,
                      activebackground=self.DM, cursor="hand2")
        self._hand_btn.pack(side="left", padx=2)

        # ── chat (expands to fill remaining space) ──
        cf=tk.Frame(self.root,bg=self.AC,bd=1)
        cf.pack(fill="both",expand=True,padx=10,pady=(0,4))
        self.chat=tk.Text(cf,bg="#030508",fg=self.TX,
                          font=("Courier New",9),wrap="word",state="disabled",
                          bd=0,padx=8,pady=6,insertbackground=self.AC,
                          selectbackground=self.AC2)
        sb=tk.Scrollbar(cf,command=self.chat.yview,bg=self.BG,
                        troughcolor=self.BG,bd=0)
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y")
        self.chat.pack(fill="both",expand=True)
        for tag,fg,font in [
            ("you", self.GR,  ("Courier New",9,"bold")),
            ("blk", self.AC,  ("Courier New",9,"bold")),
            ("act", self.AC2, ("Courier New",8,)),
            ("bod", self.TX,  ("Courier New",9,)),
            ("tim", self.DM,  ("Courier New",7,)),
        ]:
            self.chat.tag_config(tag,foreground=fg,font=font)

    # ── orb ───────────────────────────────────────────────────────────────
    def _draw_orb(self, s):
        c=self.orb; c.delete("all"); cx=cy=40
        pulse = self._pulse%3 if s in("listening","speaking","thinking","activated") else 0
        r=22+pulse
        cols={"idle":(self.DM,"#1a2a4a"),"waiting_wake_word":(self.DM,"#0d1526"),
              "activated":(self.AC,"#002244"),"listening":(self.GR,"#001a2a"),
              "thinking":(self.AC2,"#1a0a33"),"speaking":(self.AC,"#002233"),
              "no_mic":(self.RD,"#1a0505")}
        ring,fill=cols.get(s,(self.DM,"#0d1526"))
        for i in range(6,0,-1):
            c.create_oval(cx-r-i*4,cy-r-i*4,cx+r+i*4,cy+r+i*4,outline=ring,width=1)
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill=fill,outline=ring,width=2)
        c.create_text(cx,cy,text="◈",fill=ring,font=("Courier New",18,"bold"))
        self._orb_state=s

    def _tick(self):
        self._pulse+=1
        self._draw_orb(self._orb_state)
        self.root.after(400, self._tick)

    # ── chat ──────────────────────────────────────────────────────────────
    def _log(self, who, text):
        self.chat.config(state="normal")
        t=datetime.datetime.now().strftime("%H:%M")
        if who=="YOU":
            self.chat.insert("end",f"\n[{t}] ","tim")
            self.chat.insert("end","YOU:   ","you")
            self.chat.insert("end",text+"\n","bod")
        elif who=="BLK":
            self.chat.insert("end",f"\n[{t}] ","tim")
            self.chat.insert("end","BLACK: ","blk")
            self.chat.insert("end",text+"\n","bod")
        else:
            self.chat.insert("end",f"  ⚡ {text}\n","act")
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _clear(self):
        self.chat.config(state="normal"); self.chat.delete("1.0","end")
        self.chat.config(state="disabled")

    # ── event handler ─────────────────────────────────────────────────────
    def _event(self, ev, data=None):
        self.root.after(0, self._do_event, ev, data)

    def _do_event(self, ev, data=None):
        sm={"idle":'Say  " BLACK "  to wake',
            "waiting_wake_word":'👂 Waiting for  " BLACK " ...',
            "activated":"✓ Say your command now",
            "listening":"🎤 Listening...",
            "thinking":"⚙  Thinking...",
            "speaking":"🔊 Speaking...",
            "no_mic":"⚠  No mic — use text or 🎤 button"}
        if ev=="status":
            self.slbl.config(text=sm.get(data,str(data)))
            self._draw_orb(data)
            self.mbtn.config(bg=self.GR if data=="listening" else self.DM)
        elif ev=="user_text": self._log("YOU", data)
        elif ev=="ai_text":   self._log("BLK", data)
        elif ev=="action":    self._log("ACT", data)

    # ── actions ───────────────────────────────────────────────────────────
    def _entry_focus_in(self, e=None):
        if self.ent.get()=="Type a command...":
            self.ent.delete(0,"end")
            self.ent.config(fg="#ffffff")

    def _entry_focus_out(self, e=None):
        if not self.ent.get().strip():
            self.ent.insert(0,"Type a command...")
            self.ent.config(fg="#557799")

    def _send(self, e=None):
        t=self.ent.get().strip()
        if t and t!="Type a command...":
            self.ent.delete(0,"end")
            self.ent.insert(0,"Type a command...")
            self.ent.config(fg="#557799")
            self.core.send(t)

    def _mic_click(self):
        self.core.manual_listen()

    def _screen(self):
        self.core.send("analyze my screen — describe everything and fix any errors")

    def _sysinfo(self):
        self.core.send("show me system info")

    def _open_hand_mouse(self):
        if not HAND_OK:
            self._log("BLK",
                "Hand mouse needs opencv & mediapipe, Sir.\n"
                "Run: py -3.11 -m pip install opencv-python mediapipe")
            return
        try:
            ui = HandMouseUI(parent_root=self.root)
            ui.win.focus_force()
        except Exception as e:
            self._log("BLK", f"Hand mouse error: {e}")

    def _apikey(self):
        pop=tk.Toplevel(self.root)
        pop.title("API Key"); pop.configure(bg=self.BG)
        pop.geometry("360x140"); pop.attributes("-topmost",True)
        tk.Label(pop,text="Gemini API Key:",bg=self.BG,fg=self.TX,
                 font=("Courier New",9)).pack(pady=(14,4))
        e=tk.Entry(pop,bg="#030508",fg=self.TX,insertbackground=self.AC,
                   font=("Courier New",9),width=44,show="*",
                   highlightthickness=1,highlightcolor=self.AC,
                   highlightbackground=self.DM,bd=0)
        e.pack(ipady=5)
        if self.core.brain.api_key: e.insert(0,self.core.brain.api_key)
        def save():
            self.core.set_key(e.get().strip())
            self._log("BLK","API key saved, Sir."); pop.destroy()
        tk.Button(pop,text="Save",bg=self.AC2,fg="white",bd=0,
                  font=("Courier New",9),padx=18,pady=5,
                  command=save,cursor="hand2").pack(pady=10)

    def _ds(self,e): self._drag={"x":e.x_root-self.root.winfo_x(),"y":e.y_root-self.root.winfo_y()}
    def _dm(self,e): self.root.geometry(f"+{e.x_root-self._drag['x']}+{e.y_root-self._drag['y']}")
    def _min(self):  self.root.iconify()

    def _show_mic_test(self):
        pop = tk.Toplevel(self.root)
        pop.title("Microphone Test")
        pop.configure(bg=self.BG)
        sw=self.root.winfo_screenwidth(); sh=self.root.winfo_screenheight()
        pop.geometry(f"390x300+{sw//2-195}+{sh//2-150}")
        pop.attributes("-topmost", True)
        pop.resizable(False, False)

        tk.Label(pop, text="⬡  B L A C K", bg=self.BG, fg=self.AC,
                 font=("Courier New",14,"bold")).pack(pady=(16,2))
        tk.Label(pop, text="Microphone Setup & Test", bg=self.BG, fg=self.TX,
                 font=("Courier New",10,"bold")).pack(pady=(0,10))

        # animated orb canvas
        oc = tk.Canvas(pop, width=60, height=60, bg=self.BG, highlightthickness=0)
        oc.pack()
        self._test_anim = True
        self._test_step = 0
        def anim():
            if not self._test_anim: return
            oc.delete("all")
            r = 18 + (self._test_step % 4)
            oc.create_oval(30-r,30-r,30+r,30+r, fill="#001a2a", outline=self.AC, width=2)
            oc.create_text(30,30, text="◈", fill=self.AC, font=("Courier New",14,"bold"))
            self._test_step += 1
            pop.after(350, anim)
        anim()

        msg = tk.StringVar(value="Checking microphone hardware...")
        msg_lbl = tk.Label(pop, textvariable=msg, bg=self.BG, fg="#ffcc00",
                           font=("Courier New",9), wraplength=360, justify="center")
        msg_lbl.pack(pady=10)

        bf = tk.Frame(pop, bg=self.BG)
        bf.pack(pady=6)

        def set_msg(text, color="#ffcc00"):
            def _do():
                try:
                    if pop.winfo_exists():
                        msg.set(text)
                        msg_lbl.config(fg=color)
                except Exception:
                    pass
            pop.after(0, _do)

        def do_test():
            set_msg("🎤  Say something now...  (listening for 5 seconds)", "#ffcc00")
            def _test():
                if not SR_OK:
                    set_msg("❌  SpeechRecognition not installed.\n"
                            "Run:  py -3.11 -m pip install SpeechRecognition pyaudio", self.RD)
                    return
                if not self.core.mic.ok:
                    set_msg("❌  No microphone found.\n"
                            "Run:  py -3.11 -m pip install pyaudio\n"
                            "Then restart BLACK.", self.RD)
                    return
                heard = self.core.mic.listen(timeout=5, limit=8)
                if heard:
                    set_msg(f"✅  Mic working!  Heard: \"{heard}\"\n"
                            f"Voice commands are ready, Sir.", self.GR)
                else:
                    set_msg("⚠   Mic detected but nothing heard.\n"
                            "Tips:\n"
                            "1. Speak louder and closer to mic\n"
                            "2. Check mic is not muted in Windows Sound Settings\n"
                            "3. Set mic volume to 100 in Sound Settings\n"
                            "Text input still works fine.", "#ffcc00")
            threading.Thread(target=_test, daemon=True).start()

        def done():
            self._test_anim = False
            pop.destroy()
            self.root.after(200, lambda: self._log("BLK",
                "Systems online. Say BLACK to activate, Sir. Or type below."))
            self.root.after(500, lambda: self.core.speaker.say(
                "BLACK online. Say Black to activate, Sir."))

        tk.Button(bf, text="  🎤 Test Mic  ", bg=self.AC2, fg="white", bd=0,
                  font=("Courier New",10,"bold"), padx=14, pady=7,
                  command=do_test, cursor="hand2").pack(side="left", padx=8)
        tk.Button(bf, text="  Continue →  ", bg="#1a2a44", fg=self.TX, bd=0,
                  font=("Courier New",10), padx=14, pady=7,
                  command=done, cursor="hand2").pack(side="left", padx=8)

        pop.protocol("WM_DELETE_WINDOW", done)
        pop.after(800, do_test)   # auto-start test after 800ms

    def run(self):
        self.root.after(300, self._show_mic_test)
        self.root.mainloop()

# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    BlackUI().run()
