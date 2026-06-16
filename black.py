"""
BLACK - AI Desktop Assistant  (Stable Build)
Wake word : BLACK
"""
import sys, platform, ctypes
# Set Windows DPI awareness to align logical & physical coordinates
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import threading, time, os, subprocess, json, base64
import tkinter as tk, datetime, io

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
    from PIL import ImageGrab, Image, ImageDraw, ImageFont
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.02
    GUI_OK = True
except ImportError:
    GUI_OK = False

try:
    import pyperclip
    CLIP_OK = True
except ImportError:
    CLIP_OK = False

try:
    from google import genai as _genai
    from google.genai import types as _gtypes
    GEMINI_OK = True
except ImportError:
    GEMINI_OK = False

OS_NAME   = platform.system()
WAKE_WORD = "black"

# ── API key persistence ────────────────────────────────────────────────────────
_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def _load_key():
    k = os.environ.get("GEMINI_API_KEY", "")
    if k: return k
    if os.path.exists(_ENV):
        try:
            with open(_ENV, "r") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        return line.split("=",1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return ""

def _save_key(k):
    lines = []
    if os.path.exists(_ENV):
        try:
            with open(_ENV, "r") as f:
                lines = f.readlines()
        except Exception:
            pass
    lines = [l for l in lines if not l.startswith("GEMINI_API_KEY=")]
    lines.append(f"GEMINI_API_KEY={k}\n")
    try:
        with open(_ENV, "w") as f:
            f.writelines(lines)
    except Exception:
        pass

API_KEY = _load_key() or "AIzaSyAHgyQLAWUNbwS5aC6AELmC7u0TDalcg6k"
if not _load_key():
    _save_key(API_KEY)

# ── Screen geometry ────────────────────────────────────────────────────────────
if GUI_OK:
    SCR_W, SCR_H = pyautogui.size()
else:
    SCR_W, SCR_H = 1920, 1080
AI_W, AI_H = 1280, 720
print(f"[SCREEN] {SCR_W}x{SCR_H}")

# ── Click Calibration Loading ──────────────────────────────────────────────────
def _load_calibration():
    # 1. First, try auto-calibration (multimonitor offset detection)
    ox, oy = 0, 0
    try:
        import mss
        with mss.mss() as sct:
            if len(sct.monitors) > 1:
                # sct.monitors[1] is primary monitor
                mon = sct.monitors[1]
                ox = mon.get("left", 0)
                oy = mon.get("top", 0)
                print(f"[AUTO-CAL] Detected primary monitor offset: X={ox:+d}, Y={oy:+d}")
    except Exception as e:
        print(f"[AUTO-CAL] Multi-monitor check skipped: {e}")

    # 2. Next, check if manual calibration.json exists to apply fine-tuning offsets on top!
    calib_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibration.json")
    try:
        if os.path.exists(calib_file):
            with open(calib_file, "r") as f:
                d = json.load(f)
            screen = d.get("screen", [])
            mx = int(d.get("offset_x", 0))
            my = int(d.get("offset_y", 0))
            if screen and len(screen) == 2:
                sw, sh = screen[0], screen[1]
                if sw != SCR_W or sh != SCR_H:
                    mx = int(mx * SCR_W / sw)
                    my = int(my * SCR_H / sh)
            ox += mx
            oy += my
            print(f"[CAL] Combined auto-cal with manual calibration.json: X={ox:+d}, Y={oy:+d}")
    except Exception as e:
        print(f"[CAL] Fine-tuning skip: {e}")
        
    return ox, oy

CALIB_OX, CALIB_OY = _load_calibration()

def _to_screen(ax, ay):
    try:
        if ax is None or ay is None:
            return None, None
        ax_f = float(ax)
        ay_f = float(ay)
    except (ValueError, TypeError):
        return None, None
    
    sx = int(ax_f * SCR_W / AI_W) + CALIB_OX
    sy = int(ay_f * SCR_H / AI_H) + CALIB_OY
    return (max(0, min(sx, SCR_W-1)),
            max(0, min(sy, SCR_H-1)))

# ── Grid screenshot ────────────────────────────────────────────────────────────
def grab_screen():
    if not PIL_OK: return None
    try:
        img = ImageGrab.grab(all_screens=False)
        if img.size != (SCR_W, SCR_H):
            img = img.resize((SCR_W, SCR_H), Image.LANCZOS)
        img = img.resize((AI_W, AI_H), Image.LANCZOS)

        draw = ImageDraw.Draw(img, "RGBA")
        W, H = AI_W, AI_H
        
        # 1. Subtle holographic grid lines
        for x in range(0, W, 50):
            color = (0, 200, 255, 25) if x % 100 != 0 else (0, 200, 255, 55)
            width = 1 if x % 100 != 0 else 2
            draw.line([(x, 0), (x, H)], fill=color, width=width)
        for y in range(0, H, 50):
            color = (0, 200, 255, 25) if y % 100 != 0 else (0, 200, 255, 55)
            width = 1 if y % 100 != 0 else 2
            draw.line([(0, y), (W, y)], fill=color, width=width)

        # Fonts
        try:
            fn = ImageFont.truetype("consolas.ttf", 9)
            fb = ImageFont.truetype("consolas.ttf", 10)
        except:
            try:
                fn = ImageFont.truetype("arial.ttf", 9)
                fb = ImageFont.truetype("arialbd.ttf", 10)
            except:
                fn = fb = ImageFont.load_default()

        # Ruler thicknesses
        r_top = 25
        r_bottom = 25
        r_left = 35
        r_right = 35

        # 2. Draw border rulers background (dark blue/black transparent)
        draw.rectangle([0, 0, W, r_top], fill=(2, 6, 18, 230))
        draw.line([(0, r_top), (W, r_top)], fill=(0, 212, 255, 255), width=2)

        draw.rectangle([0, H - r_bottom, W, H], fill=(2, 6, 18, 230))
        draw.line([(0, H - r_bottom), (W, H - r_bottom)], fill=(0, 212, 255, 255), width=2)

        draw.rectangle([0, 0, r_left, H], fill=(2, 6, 18, 230))
        draw.line([(r_left, 0), (r_left, H)], fill=(0, 212, 255, 255), width=2)

        draw.rectangle([W - r_right, 0, W, H], fill=(2, 6, 18, 230))
        draw.line([(W - r_right, 0), (W - r_right, H)], fill=(0, 212, 255, 255), width=2)

        # 3. Draw X-axis tick marks & labels
        for x in range(0, W + 1, 10):
            # Top
            if x % 100 == 0:
                draw.line([(x, 5), (x, r_top)], fill=(0, 212, 255, 200), width=2)
                draw.text((x + 2, 2), str(x), fill=(255, 255, 0, 255), font=fn)
            elif x % 50 == 0:
                draw.line([(x, 12), (x, r_top)], fill=(0, 212, 255, 150), width=1)
            elif x % 10 == 0:
                draw.line([(x, 18), (x, r_top)], fill=(0, 212, 255, 100), width=1)
            # Bottom
            if x % 100 == 0:
                draw.line([(x, H - r_bottom), (x, H - 5)], fill=(0, 212, 255, 200), width=2)
                draw.text((x + 2, H - r_bottom + 12), str(x), fill=(255, 255, 0, 255), font=fn)
            elif x % 50 == 0:
                draw.line([(x, H - r_bottom), (x, H - 12)], fill=(0, 212, 255, 150), width=1)
            elif x % 10 == 0:
                draw.line([(x, H - r_bottom), (x, H - 18)], fill=(0, 212, 255, 100), width=1)

        # 4. Draw Y-axis tick marks & labels
        for y in range(0, H + 1, 10):
            # Left
            if y % 100 == 0:
                draw.line([(5, y), (r_left, y)], fill=(0, 212, 255, 200), width=2)
                draw.text((2, y + 2), str(y), fill=(255, 255, 0, 255), font=fn)
            elif y % 50 == 0:
                draw.line([(12, y), (r_left, y)], fill=(0, 212, 255, 150), width=1)
            elif y % 10 == 0:
                draw.line([(18, y), (r_left, y)], fill=(0, 212, 255, 100), width=1)
            # Right
            if y % 100 == 0:
                draw.line([(W - r_right, y), (W - 5, y)], fill=(0, 212, 255, 200), width=2)
                draw.text((W - r_right + 12, y + 2), str(y), fill=(255, 255, 0, 255), font=fn)
            elif y % 50 == 0:
                draw.line([(W - r_right, y), (W - 12, y)], fill=(0, 212, 255, 150), width=1)
            elif y % 10 == 0:
                draw.line([(W - r_right, y), (W - 18, y)], fill=(0, 212, 255, 100), width=1)

        # 5. Draw cursor overlay representing current mouse location
        if GUI_OK:
            try:
                cpx, cpy = pyautogui.position()
                # Translate screen coordinates to 1280x720 image coordinates
                icx = max(r_left + 5, min(W - r_right - 5, int((cpx - CALIB_OX) * W / SCR_W)))
                icy = max(r_top + 5, min(H - r_bottom - 5, int((cpy - CALIB_OY) * H / SCR_H)))

                # Glow crosshair
                draw.ellipse([icx-18, icy-18, icx+18, icy+18], outline=(0, 255, 80, 255), width=2)
                draw.line([(icx-30, icy), (icx+30, icy)], fill=(0, 255, 80, 255), width=1)
                draw.line([(icx, icy-30), (icx, icy+30)], fill=(0, 255, 80, 255), width=1)
                draw.ellipse([icx-4, icy-4, icx+4, icy+4], fill=(0, 255, 80, 255))

                # Tooltip box
                lx = icx + 22 if icx < W - 180 else icx - 172
                ly = icy - 32 if icy > r_top + 32 else icy + 22
                draw.rectangle([lx, ly, lx + 150, ly + 28], fill=(0, 0, 0, 220), outline=(0, 255, 80, 255), width=1)
                draw.text((lx + 6, ly + 3), f"img: {icx},{icy}", fill=(255, 255, 100, 255), font=fn)
                draw.text((lx + 6, ly + 14), f"scr: {cpx},{cpy}", fill=(180, 255, 180, 255), font=fn)
            except:
                pass

        buf = io.BytesIO()
        img.save(buf, "PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[SCREEN] {e}")
        return None

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You are BLACK, an elite AI desktop assistant with full vision and control.
Always call the user Sir. Reply ONLY with valid JSON — no markdown, no extra text:
{{"speech":"<say this>","actions":[{{"type":"<action>","params":{{}}}}],"need_screen":false}}
Set need_screen:true to see the screen again after actions.

COORDINATE GRAPH: Screenshots are 1280x720 with a coordinate grid and rulers on the borders.
Rulers at the borders (top, bottom, left, right) show exact X and Y coordinates.
Grid lines are drawn every 50 pixels, with thicker lines every 100 pixels.
Green target crosshair = where cursor is RIGHT NOW (with image and screen coords).
To click accurately: locate target element -> align it with border rulers to find its X and Y coordinates in 1280x720 space -> execute click(x, y).
Screen={SCR_W}x{SCR_H}. Coords auto-scaled. No calibration needed.

ACTIONS:
open_app(app,wait) | open_url(url) | shutdown | restart | lock | sleep | sys_info
vol_up(step) | vol_down(step) | mute
click(x,y) | dbl_click(x,y) | right_click(x,y) | move_to(x,y) | scroll(direction,amount)
type_text(text) | press_key(key) | hotkey(keys:[])
play_pause | next_track | prev_track
activate_hand_mouse | search_web(query) | wait(seconds) | say_only

RULES:
1. open_app → always wait 3-4s before any click
2. Multi-step tasks: use need_screen:true between steps to verify state
3. "activate hand mouse" or "hand gesture" → use activate_hand_mouse action
4. Never say "I can't" — always attempt the best approach
5. Do NOT say "Task completed" in speech — added automatically
"""

# ── AI Brain ───────────────────────────────────────────────────────────────────
class Brain:
    def __init__(self, key):
        self.key = key
        self.history = []

    def think(self, prompt, screen_b64=None):
        if not self.key:
            return {"speech":"No API key Sir. Click 🔑","actions":[],"need_screen":False}
        if not GEMINI_OK:
            return {"speech":"Run: pip install google-genai","actions":[],"need_screen":False}
        try:
            client = _genai.Client(api_key=self.key)
            contents = []
            for h in self.history[-20:]:
                contents.append(_gtypes.Content(
                    role="user" if h["role"]=="user" else "model",
                    parts=[_gtypes.Part.from_text(text=str(h["parts"][0]))]))
            cur = []
            if screen_b64:
                cur.append(_gtypes.Part.from_bytes(
                    data=base64.b64decode(screen_b64), mime_type="image/png"))
            cur.append(_gtypes.Part.from_text(text=prompt))
            contents.append(_gtypes.Content(role="user", parts=cur))
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=_gtypes.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=2000,
                    temperature=0.1))
            raw = resp.text.strip().replace("```json","").replace("```","").strip()
            result = json.loads(raw)
            self.history += [{"role":"user","parts":[prompt]},
                             {"role":"model","parts":[raw]}]
            return result
        except json.JSONDecodeError:
            return {"speech":"Understood Sir.","actions":[],"need_screen":False}
        except Exception as e:
            print(f"[AI] {e}")
            return {"speech":f"Error: {str(e)[:100]}","actions":[],"need_screen":False}

# ── Speaker ────────────────────────────────────────────────────────────────────
class Speaker:
    def __init__(self):
        self._q=[]; self._lock=threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _speak_win(self, text):
        safe = text.replace("'"," ").replace('"',' ')
        cmd  = (f"Add-Type -AssemblyName System.Speech;"
                f"$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                f"$s.Rate=1;$s.Volume=100;$s.Speak('{safe}');$s.Dispose()")
        try:
            subprocess.run(["powershell","-NonInteractive","-Command",cmd],
                           timeout=60, capture_output=True)
            return True
        except Exception as e:
            print(f"[TTS] {e}"); return False

    def _speak_py(self, text):
        if not TTS_OK: return False
        try:
            eng = pyttsx3.init()
            eng.setProperty("rate",160); eng.setProperty("volume",1.0)
            eng.say(text); eng.runAndWait()
            try: eng.stop()
            except: pass
            return True
        except Exception as e:
            print(f"[TTS-py] {e}"); return False

    def _run(self):
        while True:
            if self._q:
                with self._lock: text = self._q.pop(0)
                print(f"[BLACK]: {text}")
                if OS_NAME=="Windows":
                    if not self._speak_win(text): self._speak_py(text)
                else:
                    self._speak_py(text)
            else:
                time.sleep(0.05)

    def say(self, text):
        if not text or not text.strip(): return
        with self._lock:
            if not self._q or self._q[-1] != text:
                self._q.append(text)

# ── Microphone ─────────────────────────────────────────────────────────────────
class Mic:
    def __init__(self):
        self.ok = SR_OK
        if SR_OK:
            self.rec = sr.Recognizer()
            self.rec.energy_threshold        = 50
            self.rec.dynamic_energy_threshold = False
            self.rec.pause_threshold          = 0.5
            self.rec.phrase_threshold         = 0.1
            self.rec.non_speaking_duration    = 0.3

    def calibrate(self):
        if not self.ok: return
        try:
            with sr.Microphone() as src:
                self.rec.adjust_for_ambient_noise(src, duration=0.8)
                self.rec.energy_threshold = min(self.rec.energy_threshold, 80)
                self.rec.dynamic_energy_threshold = False
                print(f"[MIC] Ready. threshold={self.rec.energy_threshold:.0f}")
        except OSError:
            print("[MIC] No microphone found."); self.ok = False
        except Exception as e:
            print(f"[MIC] {e}"); self.ok = False

    def listen(self, timeout=4, limit=15):
        if not self.ok: return None
        try:
            with sr.Microphone() as src:
                audio = self.rec.listen(src, timeout=timeout, phrase_time_limit=limit)
            try:
                import audioop
                raw = audioop.mul(audio.get_raw_data(), audio.sample_width, 3)
                audio = sr.AudioData(raw, audio.sample_rate, audio.sample_width)
            except: pass
            text = self.rec.recognize_google(audio, language="en-IN")
            print(f"[MIC] '{text}'")
            return text.lower()
        except sr.WaitTimeoutError: return None
        except sr.UnknownValueError: return None
        except Exception as e:
            print(f"[MIC] {e}"); return None

# ── System Controller ──────────────────────────────────────────────────────────
class SysCtrl:
    @staticmethod
    def _run(cmd, shell=False):
        try:
            r = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=15)
            return r.stdout.strip() or r.stderr.strip() or "ok"
        except Exception as e: return f"err:{e}"

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
        return self._run("xdg-screensaver lock",shell=True)
    def sleep(self):
        if OS_NAME=="Windows": return self._run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0",shell=True)
        return self._run("systemctl suspend",shell=True)
    def vol_up(self, step=10):
        if OS_NAME=="Windows" and GUI_OK:
            for _ in range(max(1,step//2)): pyautogui.press("volumeup")
            return "vol up"
        if OS_NAME=="Darwin": return self._run(["osascript","-e",f"set volume output volume (output volume of (get volume settings)+{step})"])
        return self._run(f"amixer -D pulse sset Master {step}%+",shell=True)
    def vol_down(self, step=10):
        if OS_NAME=="Windows" and GUI_OK:
            for _ in range(max(1,step//2)): pyautogui.press("volumedown")
            return "vol down"
        if OS_NAME=="Darwin": return self._run(["osascript","-e",f"set volume output volume (output volume of (get volume settings)-{step})"])
        return self._run(f"amixer -D pulse sset Master {step}%-",shell=True)
    def mute(self):
        if OS_NAME=="Windows" and GUI_OK: pyautogui.press("volumemute"); return "muted"
        if OS_NAME=="Darwin": return self._run(["osascript","-e","set volume with output muted"])
        return self._run("amixer -D pulse sset Master toggle",shell=True)
    def open_app(self, name, wait=3.5):
        W={"spotify":"spotify.exe","chrome":"chrome.exe","notepad":"notepad.exe",
           "calculator":"calc.exe","explorer":"explorer.exe","firefox":"firefox.exe",
           "vlc":"vlc.exe","word":"winword.exe","excel":"excel.exe","paint":"mspaint.exe",
           "cmd":"cmd.exe","whatsapp":"WhatsApp.exe","telegram":"Telegram.exe",
           "discord":"Discord.exe","vscode":"code.exe","vs code":"code.exe","edge":"msedge.exe"}
        n = name.lower().strip()
        if OS_NAME=="Windows": self._run(f'start "" "{W.get(n,name)}"',shell=True)
        elif OS_NAME=="Darwin": self._run(["open","-a",name])
        else: self._run(f"{name} &",shell=True)
        time.sleep(float(wait)); return f"opened {name}"
    def open_url(self, url):
        import webbrowser; webbrowser.open(url); time.sleep(2.5); return f"opened {url}"
    def click(self, x=None, y=None):
        if not GUI_OK: return "no pyautogui"
        rx, ry = _to_screen(x, y)
        if rx is not None and ry is not None:
            print(f"[EXEC] click AI=({x},{y}) → Screen=({rx},{ry})")
            pyautogui.moveTo(rx,ry,duration=0.15); time.sleep(0.08); pyautogui.click()
        else:
            print(f"[EXEC] click current cursor position")
            pyautogui.click()
        time.sleep(0.2); return f"click {x},{y}"
    def dbl_click(self, x=None, y=None):
        if not GUI_OK: return "no pyautogui"
        rx, ry = _to_screen(x, y)
        if rx is not None and ry is not None:
            print(f"[EXEC] dbl_click AI=({x},{y}) → Screen=({rx},{ry})")
            pyautogui.moveTo(rx,ry,duration=0.15); time.sleep(0.08); pyautogui.doubleClick()
        else:
            print(f"[EXEC] dbl_click current cursor position")
            pyautogui.doubleClick()
        time.sleep(0.2); return "dbl click"
    def right_click(self, x=None, y=None):
        if not GUI_OK: return "no pyautogui"
        rx, ry = _to_screen(x, y)
        if rx is not None and ry is not None:
            print(f"[EXEC] right_click AI=({x},{y}) → Screen=({rx},{ry})")
            pyautogui.moveTo(rx,ry,duration=0.15); time.sleep(0.08); pyautogui.rightClick()
        else:
            print(f"[EXEC] right_click current cursor position")
            pyautogui.rightClick()
        return "right click"
    def move_to(self, x, y):
        if not GUI_OK: return "no pyautogui"
        rx, ry = _to_screen(x, y)
        if rx is not None and ry is not None:
            print(f"[EXEC] move_to AI=({x},{y}) → Screen=({rx},{ry})")
            pyautogui.moveTo(rx,ry,duration=0.2)
            return f"moved {rx},{ry}"
        return "move_to ignored: invalid coords"
    def scroll(self, direction="down", amount=3):
        if not GUI_OK: return "no pyautogui"
        pyautogui.scroll(amount if direction=="up" else -amount); return f"scroll {direction}"
    def type_text(self, text):
        if not GUI_OK: return "no pyautogui"
        import random
        time.sleep(0.3)
        # Instead of copy-paste, type character by character like a human with random delays
        for char in str(text):
            if char == '\n':
                pyautogui.press('enter')
                delay = random.uniform(0.2, 0.4)
            elif char == '\t':
                pyautogui.press('tab')
                delay = random.uniform(0.1, 0.25)
            else:
                pyautogui.write(char)
                if char == ' ':
                    delay = random.uniform(0.06, 0.12)
                elif char in '.,!?()':
                    delay = random.uniform(0.15, 0.3)
                else:
                    delay = random.uniform(0.02, 0.07)
            time.sleep(delay)
        return f"typed:{text}"
    def press_key(self, key):
        if not GUI_OK: return "no pyautogui"
        pyautogui.press(key); return f"press {key}"
    def hotkey(self, *keys):
        if not GUI_OK: return "no pyautogui"
        pyautogui.hotkey(*keys); return f"hotkey {keys}"
    def play_pause(self):
        if GUI_OK: pyautogui.press("playpause"); return "play/pause"
    def next_track(self):
        if GUI_OK: pyautogui.press("nexttrack"); return "next"
    def prev_track(self):
        if GUI_OK: pyautogui.press("prevtrack"); return "prev"
    def search_web(self, q):
        return self.open_url(f"https://www.google.com/search?q={q.replace(' ','+')}")
    def sys_info(self):
        info = {"os":OS_NAME,"time":datetime.datetime.now().strftime("%H:%M %d-%m-%Y")}
        try:
            import psutil
            info["cpu"]  = f"{psutil.cpu_percent(0.3):.0f}%"
            info["ram"]  = f"{psutil.virtual_memory().percent:.0f}%"
            b = psutil.sensors_battery()
            if b: info["battery"] = f"{b.percent:.0f}% {'⚡' if b.power_plugged else '🔋'}"
        except: pass
        return info
    def activate_hand_mouse(self, notify_cb=None):
        def _launch():
            try:
                from hand_mouse import HandMouse
                HandMouse(notify_cb=notify_cb).start()
            except ImportError:
                msg = "Install: pip install opencv-python mediapipe==0.10.14"
                if notify_cb: notify_cb("ai_text", msg)
                else: print(msg)
            except Exception as e:
                if notify_cb: notify_cb("ai_text", f"Hand mouse error: {e}")
        threading.Thread(target=_launch, daemon=True).start()
        return "hand mouse launching"

# ── Core Orchestrator ──────────────────────────────────────────────────────────
class BlackCore:
    def __init__(self, notify=None):
        self.ctrl    = SysCtrl()
        self.speaker = Speaker()
        self.mic     = Mic()
        self.brain   = Brain(API_KEY)
        self.notify  = notify or (lambda *a: None)
        self.active  = False
        self.running = True
        self._busy   = False
        self.task_canceled = False

    def stop_task(self):
        self.task_canceled = True
        self.speaker.say("Stopping task, Sir.")
        self.notify("ai_text", "Stopping task, Sir.")
        self.notify("status", "idle")

    def set_key(self, k):
        global API_KEY; API_KEY = k; self.brain.key = k; _save_key(k)

    def process(self, text):
        t_low = text.lower().strip()
        if t_low in ["stop", "cancel", "halt", "abort"]:
            self.stop_task()
            return

        self.task_canceled = False
        self._busy = True
        try:
            self.notify("status","thinking"); self.notify("user_text", text)
            if any(g in t_low for g in ["hand gesture", "hand gester", "hand mouse"]):
                self.speaker.say("Hand mouse activated Sir. Show your hand to the camera.")
                self._exec("activate_hand_mouse", {})
                self.notify("status", "listening" if self.active else "idle")
                return
            screen = None
            if any(w in t_low for w in
                   ["screen","analyze","analyse","fix","what's on","see","look",
                    "open","send","click","find","where","whatsapp","telegram","type"]):
                screen = grab_screen()
            if self.task_canceled: return
            result = self.brain.think(text, screen)
            if self.task_canceled: return
            self._handle(result)
        finally:
            self._busy = False
            self.notify("status","listening" if self.active else "idle")

    def _handle(self, result, depth=0):
        if self.task_canceled or depth > 10: return
        speech      = result.get("speech","")
        actions     = result.get("actions",[])
        need_screen = result.get("need_screen", False)
        if speech:
            self.notify("ai_text", speech)
            self.notify("status","speaking")
            self.speaker.say(speech)
        SKIP = {"say_only","sys_info"}
        real = [a for a in actions if a.get("type","") not in SKIP]
        for a in actions:
            if self.task_canceled:
                self.notify("status", "idle")
                return
            self._exec(a.get("type",""), a.get("params",{}))
        if need_screen:
            time.sleep(0.5)
            if self.task_canceled:
                self.notify("status", "idle")
                return
            self.notify("status","thinking")
            self.notify("action","👁 checking screen...")
            s = grab_screen()
            if s:
                if self.task_canceled:
                    self.notify("status", "idle")
                    return
                f = self.brain.think("Here is the current screen. Continue the task Sir.", s)
                if self.task_canceled:
                    self.notify("status", "idle")
                    return
                self._handle(f, depth+1); return
        if real:
            time.sleep(0.3)
            if self.task_canceled:
                self.notify("status", "idle")
                return
            self.speaker.say("Task completed, Sir.")
            self.notify("ai_text","Task completed, Sir.")

    def _exec(self, t, p):
        self.notify("action", t)
        try:
            if   t=="open_app":           self.ctrl.open_app(p.get("app",""), float(p.get("wait",3.5)))
            elif t=="open_url":           self.ctrl.open_url(p.get("url",""))
            elif t=="shutdown":           self.ctrl.shutdown()
            elif t=="restart":            self.ctrl.restart()
            elif t=="lock":               self.ctrl.lock()
            elif t=="sleep":              self.ctrl.sleep()
            elif t=="vol_up":             self.ctrl.vol_up(p.get("step",10))
            elif t=="vol_down":           self.ctrl.vol_down(p.get("step",10))
            elif t=="mute":               self.ctrl.mute()
            elif t=="click":              self.ctrl.click(p.get("x"), p.get("y"))
            elif t=="dbl_click":          self.ctrl.dbl_click(p.get("x"), p.get("y"))
            elif t=="right_click":        self.ctrl.right_click(p.get("x"), p.get("y"))
            elif t=="move_to":            self.ctrl.move_to(p.get("x",0), p.get("y",0))
            elif t=="scroll":             self.ctrl.scroll(p.get("direction","down"), p.get("amount",3))
            elif t=="type_text":          self.ctrl.type_text(p.get("text",""))
            elif t=="press_key":          self.ctrl.press_key(p.get("key",""))
            elif t=="hotkey":             self.ctrl.hotkey(*p.get("keys",[]))
            elif t=="play_pause":         self.ctrl.play_pause()
            elif t=="next_track":         self.ctrl.next_track()
            elif t=="prev_track":         self.ctrl.prev_track()
            elif t=="search_web":         self.ctrl.search_web(p.get("query",""))
            elif t=="activate_hand_mouse":
                self.ctrl.activate_hand_mouse(notify_cb=self.notify)
                self.notify("ai_text","Hand mouse activated Sir. Show your hand to the camera.")
            elif t=="sys_info":           self.notify("ai_text", str(self.ctrl.sys_info()))
            elif t=="wait":
                s = float(p.get("seconds",1)); s = s/1000 if s>100 else s; time.sleep(s)
            elif t in ("say_only","screen_snapshot"): pass
            else: print(f"[EXEC] unknown: {t}")
        except Exception as e:
            print(f"[EXEC] {t}: {e}")

    def _wake_loop(self):
        if not self.mic.ok: self.notify("status","no_mic"); return
        self.notify("status","waiting_wake_word")
        while self.running:
            if self._busy:
                # When busy with a task, listen briefly for voice abort command
                heard = self.mic.listen(timeout=1, limit=3)
                if heard and any(w in heard for w in ["stop", "cancel", "halt", "abort"]):
                    self.stop_task()
                time.sleep(0.1)
                continue

            heard = self.mic.listen(timeout=3, limit=5)
            if heard and any(w in heard for w in ["black","blank","block","blake"]):
                self.active = True
                self.notify("status","activated")
                self.speaker.say("Yes Sir, listening.")
                self.notify("ai_text","Yes Sir, listening.")
                self._get_cmd()
            time.sleep(0.02)

    def _get_cmd(self):
        self.notify("status","listening")
        cmd = self.mic.listen(timeout=10, limit=20)
        self.active = False
        if cmd:
            threading.Thread(target=self.process, args=(cmd,), daemon=True).start()
        else:
            self.speaker.say("Didn't catch that Sir.")
            self.notify("ai_text","Didn't catch that Sir.")
            self.notify("status","waiting_wake_word")

    def start_mic(self):
        self.start_mic_with_cb(None)

    def start_mic_with_cb(self, callback):
        """Calibrate mic in background, call callback(ok, message) when done."""
        def _init():
            try:
                self.mic.calibrate()
                if self.mic.ok:
                    threading.Thread(target=self._wake_loop, daemon=True).start()
                    if callback: callback(True, "Mic ready. Say BLACK to activate.")
                else:
                    self.notify("status","no_mic")
                    if callback: callback(False, "No microphone found.")
            except Exception as e:
                print(f"[MIC INIT] {e}")
                self.notify("status","no_mic")
                if callback: callback(False, f"Mic error: {e}")
        threading.Thread(target=_init, daemon=True).start()

    def send(self, text):
        threading.Thread(target=self.process, args=(text,), daemon=True).start()

    def manual_listen(self):
        if self._busy: return
        def _go():
            self._busy = True
            if not self.mic.ok:
                self.speaker.say("No microphone Sir."); self._busy = False; return
            self.notify("status","listening"); self.notify("ai_text","Listening Sir...")
            cmd = self.mic.listen(timeout=10, limit=20)
            if cmd: self.process(cmd)
            else:
                self.speaker.say("Didn't catch that Sir.")
                self.notify("ai_text","Didn't catch that Sir.")
                self.notify("status","idle")
            self._busy = False
        threading.Thread(target=_go, daemon=True).start()

# ── Floating UI ────────────────────────────────────────────────────────────────
class BlackUI:
    BG="#040a18"; AC="#00f0ff"; AC2="#ff007f"
    TX="#d1f4ff"; DM="#004b66"; GR="#00ff66"; RD="#ff3355"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BLACK")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha",   0.95)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        # Increased window height from 540 to 585 to fit the larger Arc Reactor
        self.root.geometry(f"430x585+{sw-450}+{sh-625}")
        self.root.configure(bg=self.BG)
        self._drag={}; self._orb_state="idle"; self._pulse=0
        # Core created FIRST — UI build needs it
        self.core = BlackCore(notify=self._event)
        self._build()
        # Schedule after mainloop starts — prevents daemon-thread exit race
        self.root.after(100, self._tick)
        self.root.after(300, self._startup)

    def _startup(self):
        """Runs after mainloop — window is alive, safe to start threads."""
        self._show_mic_test()   # show splash first
        self.core.start_mic_with_cb(self._on_mic_ready)  # calibrate in background

    def _on_mic_ready(self, ok, message):
        """Called by mic calibration when done."""
        if ok:
            self._update_splash(f"✅ {message}", self.GR)
        else:
            self._update_splash(f"⚠ {message}\nText input works fine.", self.RD)
        # Close splash after showing result for 1.5s
        try:
            if self.root.winfo_exists():
                self.root.after(1500, self._close_splash)
        except Exception:
            pass

    def _style_btn(self, btn, bg="#081b33", fg="#00f0ff", h_bg="#00f0ff", h_fg="#030815"):
        btn.config(bg=bg, fg=fg, activebackground=h_bg, activeforeground=h_fg, bd=0, relief="flat")
        btn.bind("<Enter>", lambda e: btn.config(bg=h_bg, fg=h_fg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg, fg=fg))

    def _build(self):
        # Title bar
        bar = tk.Frame(self.root, bg="#020612", height=40, cursor="fleur")
        bar.pack(fill="x"); bar.pack_propagate(False)
        bar.bind("<Button-1>",self._ds); bar.bind("<B1-Motion>",self._dm)
        lbl = tk.Label(bar, text="⬡  B L A C K  (J.A.R.V.I.S.)", bg="#020612", fg=self.AC,
                       font=("Consolas",12,"bold"))
        lbl.pack(side="left", padx=12, pady=9)
        lbl.bind("<Button-1>",self._ds); lbl.bind("<B1-Motion>",self._dm)
        self.mic_dot = tk.Label(bar,
            text="● MIC" if SR_OK else "● NO MIC",
            bg="#020612", fg=self.GR if SR_OK else self.RD, font=("Consolas",8,"bold"))
        self.mic_dot.pack(side="right", padx=6)
        bf = tk.Frame(bar, bg="#020612"); bf.pack(side="right", padx=4)
        
        btn_min = tk.Button(bf,text="—",bg="#020612",fg=self.DM,bd=0,font=("Consolas",12),
            command=self._min,activebackground="#020612",activeforeground=self.AC,
            cursor="hand2")
        btn_min.pack(side="left")
        btn_close = tk.Button(bf,text="✕",bg="#020612",fg=self.DM,bd=0,font=("Consolas",12),
            command=self.root.destroy,activebackground="#020612",activeforeground=self.RD,
            cursor="hand2")
        btn_close.pack(side="left",padx=(4,0))

        # Input row — packed BEFORE chat so always visible
        ir = tk.Frame(self.root, bg="#050f24", pady=6)
        ir.pack(fill="x", padx=10, pady=(8,2))
        self.ent = tk.Entry(ir, bg="#091833", fg="#ffffff", insertbackground=self.AC,
            font=("Consolas",11), bd=0, highlightthickness=1.5,
            highlightcolor=self.AC, highlightbackground=self.DM, relief="flat")
        self.ent.pack(side="left", fill="x", expand=True, ipady=9, padx=(6,6))
        self.ent.bind("<Return>", self._send)
        self.ent.insert(0,"Type a command..."); self.ent.config(fg="#004b66")
        self.ent.bind("<FocusIn>",  self._fin)
        self.ent.bind("<FocusOut>", self._fout)
        
        self.mbtn = tk.Button(ir, text="🎤", font=("Consolas",11), padx=10, pady=4,
            command=self.core.manual_listen, cursor="hand2")
        self._style_btn(self.mbtn, bg=self.AC2, fg="white", h_bg=self.GR, h_fg="black")
        self.mbtn.pack(side="left", padx=(0,4))
        
        btn_send = tk.Button(ir, text="▶", font=("Consolas",11,"bold"), padx=12, pady=4,
            command=self._send, cursor="hand2")
        self._style_btn(btn_send, bg=self.AC, fg="black", h_bg="#ffffff", h_fg="black")
        btn_send.pack(side="left")

        # Util row
        ur = tk.Frame(self.root, bg=self.BG); ur.pack(fill="x", padx=10, pady=(0,4))
        for txt,cmd in [("📷 Screen",self._screen),("🔑 API Key",self._apikey),
                         ("🗑 Clear",self._clear),("ℹ Sys",self._sysinfo),
                         ("🖐 Hand",self._hand),("⏹ Stop",self._stop)]:
            btn = tk.Button(ur,text=txt,font=("Consolas",8),padx=6,pady=3,command=cmd,cursor="hand2")
            self._style_btn(btn)
            btn.pack(side="left",padx=2)

        # Orb (Iron Man Arc Reactor)
        of = tk.Frame(self.root, bg=self.BG); of.pack(pady=(6,0))
        self.orb = tk.Canvas(of,width=120,height=120,bg=self.BG,highlightthickness=0)
        self.orb.pack(); self._draw_orb("idle")
        self.slbl = tk.Label(self.root, text='Say "BLACK" to wake',
            bg=self.BG, fg=self.DM, font=("Consolas",8,"bold"))
        self.slbl.pack(pady=(2,0))

        # Chat — fills remaining space
        cf = tk.Frame(self.root, bg=self.AC, bd=1)
        cf.pack(fill="both", expand=True, padx=10, pady=(4,8))
        self.chat = tk.Text(cf, bg="#020610", fg=self.TX, font=("Consolas",9),
            wrap="word", state="disabled", bd=0, padx=8, pady=6,
            insertbackground=self.AC, selectbackground=self.AC2)
        sb = tk.Scrollbar(cf, command=self.chat.yview, bg=self.BG, troughcolor=self.BG, bd=0)
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y"); self.chat.pack(fill="both",expand=True)
        for tag,fg,fn in [
            ("you",self.GR, ("Consolas",9,"bold")),
            ("blk",self.AC, ("Consolas",9,"bold")),
            ("act",self.AC2,("Consolas",8,)),
            ("bod",self.TX, ("Consolas",9,)),
            ("tim",self.DM, ("Consolas",7,))]:
            self.chat.tag_config(tag,foreground=fg,font=fn)

    def _draw_orb(self, s):
        c = self.orb
        c.delete("all")
        cx = cy = 60  # canvas is 120x120
        t = self._pulse
        
        theme_cols = {
            "idle": ("#00d4ff", "#001a26", "#004b66"),
            "waiting_wake_word": ("#00a8cc", "#000f1a", "#002d40"),
            "activated": ("#00ffcc", "#00261f", "#005e4c"),
            "listening": ("#00ff66", "#00260f", "#005e27"),
            "thinking": ("#ff007f", "#260013", "#5e002f"),
            "speaking": ("#00f0ff", "#001f26", "#005b6b"),
            "no_mic": ("#ff3355", "#26000c", "#5e001c")
        }
        fg, bg, mid = theme_cols.get(s, theme_cols["idle"])
        
        # Outer ring (dashed / segments)
        r_outer = 48
        c.create_oval(cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer, 
                      outline=mid, width=1)
        
        # Rotate dashed segments
        dash_offset = (t * 5) % 360
        import math
        for angle in range(0, 360, 30):
            rad = math.radians(angle + (dash_offset if s != "idle" else t))
            x1 = cx + (r_outer - 5) * math.cos(rad)
            y1 = cy + (r_outer - 5) * math.sin(rad)
            x2 = cx + (r_outer + 1) * math.cos(rad)
            y2 = cy + (r_outer + 1) * math.sin(rad)
            c.create_line(x1, y1, x2, y2, fill=mid, width=2.5)
            
        # Inner reactor chassis
        r_mid = 36
        c.create_oval(cx - r_mid, cy - r_mid, cx + r_mid, cy + r_mid, 
                      fill=bg, outline=fg, width=2)
                      
        # Coils/segments
        for i in range(10):
            angle = i * 36 + (t * 3 if s == "thinking" else t * 0.5)
            rad = math.radians(angle)
            x_c = cx + 27 * math.cos(rad)
            y_c = cy + 27 * math.sin(rad)
            cr = 4.5
            c.create_rectangle(x_c - cr, y_c - cr, x_c + cr, y_c + cr, 
                               fill=mid, outline=fg, width=1)
                               
        # Glowing inner ring
        r_inner = 18
        pulse = 0
        if s in ("listening", "speaking", "thinking"):
            pulse = math.sin(t * 0.8) * 3
        r_inner_p = r_inner + pulse
        c.create_oval(cx - r_inner_p, cy - r_inner_p, cx + r_inner_p, cy + r_inner_p, 
                      outline="#ffffff", width=2)
                      
        # Glowing core
        r_core = 10 + (pulse * 0.5)
        c.create_oval(cx - r_core, cy - r_core, cx + r_core, cy + r_core, 
                      fill="#ffffff", outline=fg, width=1)
                      
        # Triangular details for Mark VI style
        rad_t = math.radians(t * 6 if s == "thinking" else -t)
        t_pts = []
        for i in range(3):
            angle = i * 120 - 90
            rad_pt = math.radians(angle) + rad_t
            t_pts.append(cx + 7 * math.cos(rad_pt))
            t_pts.append(cy + 7 * math.sin(rad_pt))
        c.create_polygon(t_pts, fill="", outline=fg, width=1.5)
        self._orb_state = s

    def _tick(self):
        self._pulse+=1; self._draw_orb(self._orb_state); self.root.after(100,self._tick)

    def _log(self, who, text):
        try:
            if not self.root.winfo_exists(): return
            self.chat.config(state="normal")
            t = datetime.datetime.now().strftime("%H:%M")
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
            self.chat.config(state="disabled"); self.chat.see("end")
        except Exception:
            pass

    def _event(self, ev, data=None):
        try:
            if self.root.winfo_exists():
                self.root.after(0, self._do_event, ev, data)
        except Exception:
            pass

    def _do_event(self, ev, data=None):
        try:
            if not self.root.winfo_exists(): return
            sm={"idle":'Say "BLACK" to wake',
                "waiting_wake_word":'👂 Waiting for "BLACK"...',
                "activated":"✓ Speak now",
                "listening":"🎤 Listening...",
                "thinking":"⚙ Thinking...",
                "speaking":"🔊 Speaking...",
                "no_mic":"⚠ No mic — use text"}
            if ev=="status":
                self.slbl.config(text=sm.get(data,str(data)))
                self._draw_orb(data)
                self.mbtn.config(bg=self.GR if data=="listening" else self.AC2)
            elif ev=="user_text": self._log("YOU", data)
            elif ev=="ai_text":   self._log("BLK", data)
            elif ev in ("action","hand_status"): self._log("ACT", data)
        except Exception:
            pass

    def _fin(self, e=None):
        if self.ent.get()=="Type a command...":
            self.ent.delete(0,"end"); self.ent.config(fg="#ffffff")
    def _fout(self, e=None):
        if not self.ent.get().strip():
            self.ent.insert(0,"Type a command..."); self.ent.config(fg="#4a7aaa")
    def _send(self, e=None):
        t = self.ent.get().strip()
        if t and t!="Type a command...":
            self.ent.delete(0,"end")
            self.ent.insert(0,"Type a command..."); self.ent.config(fg="#4a7aaa")
            self.core.send(t)
    def _screen(self):  self.core.send("analyze my screen and describe everything you see")
    def _sysinfo(self): self.core.send("show me system info")
    def _hand(self):
        self._log("BLK","Activating hand mouse Sir...")
        self.core.ctrl.activate_hand_mouse(notify_cb=self._event)
    def _stop(self):    self.core.stop_task()
    def _clear(self):
        self.chat.config(state="normal"); self.chat.delete("1.0","end")
        self.chat.config(state="disabled")
    def _apikey(self):
        pop=tk.Toplevel(self.root); pop.title("API Key")
        pop.configure(bg=self.BG); pop.geometry("360x140")
        pop.attributes("-topmost",True)
        tk.Label(pop,text="Gemini API Key:",bg=self.BG,fg=self.TX,
                 font=("Consolas",9)).pack(pady=(14,4))
        e=tk.Entry(pop,bg="#020610",fg=self.TX,insertbackground=self.AC,
            font=("Consolas",9),width=44,show="*",highlightthickness=1,
            highlightcolor=self.AC,highlightbackground=self.DM,bd=0)
        e.pack(ipady=5)
        if self.core.brain.key: e.insert(0,self.core.brain.key)
        def save():
            self.core.set_key(e.get().strip())
            self._log("BLK","API key saved Sir."); pop.destroy()
        btn = tk.Button(pop,text="Save",font=("Consolas",9),padx=18,pady=5,command=save,cursor="hand2")
        self._style_btn(btn, bg=self.AC2, fg="white", h_bg=self.AC, h_fg="black")
        btn.pack(pady=10)

    def _show_mic_test(self):
        """Simple splash — no mic listening here, calibration runs separately."""
        pop = tk.Toplevel(self.root)
        pop.title("BLACK")
        pop.configure(bg=self.BG)
        pop.attributes("-topmost", True)
        pop.resizable(False, False)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        pop.geometry(f"360x220+{sw//2-180}+{sh//2-110}")

        tk.Label(pop, text="⬡  B L A C K", bg=self.BG, fg=self.AC,
                 font=("Consolas",14,"bold")).pack(pady=(18,4))

        self._ta = True; self._ts = 0
        oc = tk.Canvas(pop, width=70, height=70, bg=self.BG, highlightthickness=0)
        oc.pack(pady=6)

        def anim():
            if not self._ta: return
            oc.delete("all"); r = 20 + (self._ts % 4)
            oc.create_oval(35-r,35-r,35+r,35+r, fill="#001a26", outline=self.AC, width=2)
            oc.create_text(35,35, text="◈", fill=self.AC, font=("Consolas",16,"bold"))
            self._ts += 1; pop.after(300, anim)
        anim()

        self._splash_msg = tk.StringVar(value="Starting up...")
        self._splash_lbl = tk.Label(pop, textvariable=self._splash_msg,
            bg=self.BG, fg="#ffcc00", font=("Consolas",9),
            wraplength=320, justify="center")
        self._splash_lbl.pack(pady=8)

        self._splash_pop = pop
        pop.protocol("WM_DELETE_WINDOW", self._close_splash)

    def _update_splash(self, text, color="#ffcc00"):
        """Update splash message safely from any thread."""
        def _do():
            try:
                if hasattr(self,"_splash_pop") and self._splash_pop.winfo_exists():
                    self._splash_msg.set(text)
                    self._splash_lbl.config(fg=color)
            except: pass
        try:
            if self.root.winfo_exists():
                self.root.after(0, _do)
        except Exception:
            pass

    def _close_splash(self):
        """Close splash and show welcome message."""
        try:
            self._ta = False
            if hasattr(self,"_splash_pop") and self._splash_pop.winfo_exists():
                self._splash_pop.destroy()
        except: pass
        self._log("BLK", "Systems online Sir. Say BLACK to activate.")
        self.core.speaker.say("BLACK online. Say Black to activate Sir.")

    def _ds(self,e): self._drag={"x":e.x_root-self.root.winfo_x(),"y":e.y_root-self.root.winfo_y()}
    def _dm(self,e): self.root.geometry(f"+{e.x_root-self._drag['x']}+{e.y_root-self._drag['y']}")
    def _min(self):  self.root.iconify()

    def run(self):
        self.root.mainloop()

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        BlackUI().run()
    except Exception as e:
        import traceback
        print("\n[FATAL ERROR]")
        traceback.print_exc()
        input("\nPress Enter to close...")
