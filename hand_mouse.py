"""
BLACK - Hand Gesture Virtual Mouse
Uses webcam + MediaPipe to control mouse with hand gestures.

Gestures:
  ✋ Open hand / index finger up  → move mouse
  👆 Index finger point           → left click
  🤙 Middle finger up             → right click
  ✊ All fingers closed (fist)    → drag (hold left button)
  ✌  Two fingers (peace)         → scroll
"""

import threading
import time
import platform

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False

try:
    import mediapipe as mp
    MP_OK = True
except ImportError:
    MP_OK = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    GUI_OK = True
except ImportError:
    GUI_OK = False

import tkinter as tk

OS_NAME = platform.system()

# ── Gesture constants ──────────────────────────────────────────────────────────
SMOOTHING     = 6      # higher = smoother but slightly delayed
CLICK_COOLDOWN= 0.6    # seconds between clicks
SCROLL_SPEED  = 3

class HandMouse:
    def __init__(self, notify_cb=None):
        self.notify   = notify_cb or (lambda *a: None)
        self.running  = False
        self._thread  = None
        self._win     = None   # preview window (tk)

        # State
        self._prev_x  = 0
        self._prev_y  = 0
        self._drag    = False
        self._last_click = 0
        self._scroll_ref = None

        # Smoothing buffer
        self._smooth_x = []
        self._smooth_y = []

    # ── Public ─────────────────────────────────────────────────────────────────
    def start(self):
        if not CV2_OK or not MP_OK or not GUI_OK:
            self.notify("hand_status", "❌ Install: pip install opencv-python mediapipe")
            return False
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.notify("hand_status", "✅ Hand mouse active")
        return True

    def stop(self):
        self.running = False
        self.notify("hand_status", "⭕ Hand mouse off")

    # ── Core loop ──────────────────────────────────────────────────────────────
    def _loop(self):
        # ── Detect MediaPipe API version ──────────────────────────────────────
        LEGACY_API = False
        NEW_API    = False
        mp_hands_legacy = None
        mp_draw         = None

        # Try legacy solutions first (works with 0.10.14)
        try:
            import mediapipe as _mp_test
            _ = _mp_test.solutions.hands
            mp_hands_legacy = mp.solutions.hands
            mp_draw         = mp.solutions.drawing_utils
            LEGACY_API      = True
            print("[HAND] Using legacy MediaPipe solutions API")
        except Exception as e1:
            print(f"[HAND] Legacy API not available: {e1}")
            # Try new Tasks API
            try:
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision as mp_vision
                NEW_API = True
                print("[HAND] Using new MediaPipe Tasks API")
            except Exception as e2:
                print(f"[HAND] New API not available: {e2}")

        if not NEW_API and not LEGACY_API:
            self.notify("hand_status",
                "❌ MediaPipe not working.\n"
                "Run: py -3.11 -m pip install mediapipe==0.10.14 --force-reinstall")
            return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.notify("hand_status", "❌ No webcam found")
            return

        # Screen size
        import ctypes
        try:
            user32 = ctypes.windll.user32
            SCR_W  = user32.GetSystemMetrics(0)
            SCR_H  = user32.GetSystemMetrics(1)
        except Exception:
            SCR_W, SCR_H = pyautogui.size()

        print(f"[HAND] Screen: {SCR_W}x{SCR_H}  API: {'new' if NEW_API else 'legacy'}")

        def process_frame_legacy(frame, hands_ctx):
            h, w = frame.shape[:2]
            rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            res = hands_ctx.process(rgb)
            rgb.flags.writeable = True
            return res, h, w

        def draw_landmarks_legacy(frame, hand_lms):
            mp_draw.draw_landmarks(
                frame, hand_lms,
                mp_hands_legacy.HAND_CONNECTIONS,
                mp_draw.DrawingSpec(color=(0,212,255), thickness=2, circle_radius=4),
                mp_draw.DrawingSpec(color=(123,47,255), thickness=2)
            )

        def get_landmarks_new(frame):
            """Use new MediaPipe Tasks API."""
            import mediapipe as _mp
            h, w = frame.shape[:2]
            rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = _mp.Image(image_format=_mp.ImageFormat.SRGB, data=rgb)
            result   = self._new_detector.detect(mp_image)
            if result.hand_landmarks:
                # Convert to normalized landmark list matching legacy format
                class LM:
                    def __init__(self, x,y,z): self.x=x; self.y=y; self.z=z
                lms = [LM(l.x,l.y,l.z) for l in result.hand_landmarks[0]]
                return lms, h, w
            return None, h, w

        # ── Init detector ──────────────────────────────────────────────────────
        if LEGACY_API:
            hands_ctx = mp_hands_legacy.Hands(
                max_num_hands=1,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.6,
                model_complexity=0
            )
            ctx_mgr = hands_ctx
        else:
            # New API — download model if needed
            import urllib.request, os as _os
            model_path = _os.path.join(_os.path.dirname(__file__), "hand_landmarker.task")
            if not _os.path.exists(model_path):
                self.notify("hand_status", "⬇ Downloading hand model...")
                url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
                urllib.request.urlretrieve(url, model_path)
            from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
            options = HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=model_path),
                running_mode=RunningMode.IMAGE,
                num_hands=1,
                min_hand_detection_confidence=0.7,
                min_hand_presence_confidence=0.6,
                min_tracking_confidence=0.5
            )
            self._new_detector = HandLandmarker.create_from_options(options)

        def run_with_legacy():
            with hands_ctx:
                while self.running:
                    ret, frame = cap.read()
                    if not ret:
                        time.sleep(0.05); continue
                    frame  = cv2.flip(frame, 1)
                    res, h, w = process_frame_legacy(frame, hands_ctx)
                    lm_list = None
                    if res.multi_hand_landmarks:
                        lm_list = res.multi_hand_landmarks[0].landmark
                        draw_landmarks_legacy(frame, res.multi_hand_landmarks[0])
                    self._process_gesture(frame, lm_list, h, w, SCR_W, SCR_H)
                    cv2.imshow("BLACK - Hand Mouse (Q to quit)", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'): break

        def run_with_new():
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05); continue
                frame = cv2.flip(frame, 1)
                lm_list, h, w = get_landmarks_new(frame)
                self._process_gesture(frame, lm_list, h, w, SCR_W, SCR_H)
                cv2.imshow("BLACK - Hand Mouse (Q to quit)", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break

        try:
            if LEGACY_API:
                run_with_legacy()
            else:
                run_with_new()
        finally:
            cap.release()
            cv2.destroyAllWindows()
            if self._drag:
                try: pyautogui.mouseUp(button="left")
                except: pass
            self.running = False
            self.notify("hand_status", "⭕ Hand mouse stopped")

    def _process_gesture(self, frame, lm, h, w, SCR_W, SCR_H):
        """Core gesture logic — shared between legacy and new API."""
        gesture = "none"

        if lm is not None:
            # Finger up detection
            idx_up   = lm[8].y  < lm[6].y
            mid_up   = lm[12].y < lm[10].y
            ring_up  = lm[16].y < lm[14].y
            pinky_up = lm[20].y < lm[18].y
            fingers_up = sum([idx_up, mid_up, ring_up, pinky_up])

            # Mouse position from index fingertip
            ix = lm[8].x
            iy = lm[8].y
            margin = 0.15
            mx = max(0.0, min(1.0, (ix - margin) / (1 - 2*margin)))
            my = max(0.0, min(1.0, (iy - margin) / (1 - 2*margin)))
            target_x = int(mx * SCR_W)
            target_y = int(my * SCR_H)

            self._smooth_x.append(target_x)
            self._smooth_y.append(target_y)
            if len(self._smooth_x) > SMOOTHING:
                self._smooth_x.pop(0); self._smooth_y.pop(0)
            sx = int(sum(self._smooth_x) / len(self._smooth_x))
            sy = int(sum(self._smooth_y) / len(self._smooth_y))
            now = time.time()

            # FIST — drag
            if fingers_up == 0:
                gesture = "drag"
                if not self._drag:
                    pyautogui.mouseDown(button="left"); self._drag = True
                pyautogui.moveTo(sx, sy, duration=0)

            # INDEX ONLY — move + pinch = left click
            elif idx_up and not mid_up and not ring_up and not pinky_up:
                gesture = "move"
                if self._drag: pyautogui.mouseUp(button="left"); self._drag = False
                pyautogui.moveTo(sx, sy, duration=0)
                dist = ((lm[8].x-lm[4].x)**2 + (lm[8].y-lm[4].y)**2)**0.5
                if dist < 0.06 and (now-self._last_click) > CLICK_COOLDOWN:
                    pyautogui.click(sx, sy); self._last_click = now; gesture = "left_click"

            # MIDDLE ONLY — move + middle+thumb pinch = right click
            elif mid_up and not idx_up and not ring_up and not pinky_up:
                gesture = "move_mid"
                if self._drag: pyautogui.mouseUp(button="left"); self._drag = False
                pyautogui.moveTo(sx, sy, duration=0)
                mid_dist = ((lm[12].x-lm[4].x)**2 + (lm[12].y-lm[4].y)**2)**0.5
                if mid_dist < 0.07 and (now-self._last_click) > CLICK_COOLDOWN:
                    pyautogui.rightClick(sx, sy); self._last_click = now; gesture = "right_click"

            # PEACE ✌ — scroll
            elif idx_up and mid_up and not ring_up and not pinky_up:
                gesture = "scroll"
                if self._drag: pyautogui.mouseUp(button="left"); self._drag = False
                if self._scroll_ref is None: self._scroll_ref = iy
                delta = self._scroll_ref - iy
                if abs(delta) > 0.04:
                    pyautogui.scroll(int(delta * SCROLL_SPEED * 10))
                    self._scroll_ref = iy

            # OPEN HAND — just move
            else:
                gesture = "open"
                if self._drag: pyautogui.mouseUp(button="left"); self._drag = False
                self._scroll_ref = None
                pyautogui.moveTo(sx, sy, duration=0)

            # Draw gesture label
            labels = {
                "move":       ("MOVE",               (0,255,150)),
                "left_click": ("LEFT CLICK ✓",       (0,255,0)),
                "right_click":("RIGHT CLICK ✓",      (255,100,0)),
                "move_mid":   ("MID (pinch=RClick)",  (200,150,255)),
                "drag":       ("DRAG ✊",              (255,0,100)),
                "scroll":     ("SCROLL ✌",            (255,220,0)),
                "open":       ("OPEN HAND",           (0,200,255)),
            }
            lbl, col = labels.get(gesture, ("", (255,255,255)))
            cv2.putText(frame, lbl, (20,50), cv2.FONT_HERSHEY_SIMPLEX, 1.1, col, 3)

            # Cursor dot
            px, py = int(ix*w), int(iy*h)
            cv2.circle(frame, (px,py), 10, (0,212,255), -1)
            cv2.circle(frame, (px,py), 14, (255,255,255), 2)

        else:
            if self._drag: pyautogui.mouseUp(button="left"); self._drag = False
            self._smooth_x.clear(); self._smooth_y.clear(); self._scroll_ref = None
            cv2.putText(frame, "Show hand...", (20,50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (80,80,80), 2)

        # HUD
        cv2.rectangle(frame, (0,h-80), (w,h), (8,12,24), -1)
        hints = ["Index+move | Pinch=LClick", "Middle+move | Pinch=RClick",
                 "Fist=Drag | Peace=Scroll  ", "Press Q to quit            "]
        for i,hint in enumerate(hints):
            cv2.putText(frame, hint, (8,h-62+i*16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,212,255), 1)


# ── Tkinter control window ─────────────────────────────────────────────────────
class HandMouseUI:
    """Small floating control panel for hand mouse."""
    BG  = "#080c18"
    AC  = "#00d4ff"
    AC2 = "#7b2fff"
    TX  = "#ddeeff"
    GR  = "#00ff99"
    RD  = "#ff3355"

    def __init__(self, parent_root=None):
        self.hm  = HandMouse(notify_cb=self._on_notify)
        self.win = tk.Toplevel(parent_root) if parent_root else tk.Tk()
        self.win.title("Hand Mouse")
        self.win.configure(bg=self.BG)
        self.win.attributes("-topmost", True)
        self.win.geometry("300x320+20+20")
        self.win.resizable(False, False)
        self._build()

    def _build(self):
        tk.Label(self.win, text="🖐  Hand Mouse",
                 bg=self.BG, fg=self.AC,
                 font=("Courier New",13,"bold")).pack(pady=(14,4))

        self._status_var = tk.StringVar(value="⭕ Off")
        tk.Label(self.win, textvariable=self._status_var,
                 bg=self.BG, fg="#ffcc00",
                 font=("Courier New",9), wraplength=280).pack(pady=4)

        # Toggle button
        self._btn_var = tk.StringVar(value="▶  Start Hand Mouse")
        self._btn = tk.Button(self.win, textvariable=self._btn_var,
                              bg=self.AC2, fg="white", bd=0,
                              font=("Courier New",10,"bold"),
                              padx=14, pady=8,
                              command=self._toggle,
                              cursor="hand2")
        self._btn.pack(pady=8)

        # Gesture guide
        guide_frame = tk.Frame(self.win, bg="#0d1426", padx=10, pady=10)
        guide_frame.pack(fill="x", padx=12, pady=4)
        tk.Label(guide_frame, text="GESTURES", bg="#0d1426",
                 fg=self.AC, font=("Courier New",8,"bold")).pack(anchor="w")

        gestures = [
            ("☝  Index up + move",      "Move cursor"),
            ("🤏 Index + thumb pinch",  "Left click"),
            ("🖕  Middle + thumb pinch","Right click"),
            ("✊ Fist (all closed)",    "Drag"),
            ("✌  Peace sign",           "Scroll up/down"),
        ]
        for gesture, action in gestures:
            row = tk.Frame(guide_frame, bg="#0d1426")
            row.pack(fill="x", pady=1)
            tk.Label(row, text=gesture, bg="#0d1426", fg=self.TX,
                     font=("Courier New",8), width=22, anchor="w").pack(side="left")
            tk.Label(row, text=action, bg="#0d1426", fg=self.GR,
                     font=("Courier New",8), anchor="w").pack(side="left")

        tk.Label(self.win, text="Press Q in camera window to stop",
                 bg=self.BG, fg="#3a5a7a",
                 font=("Courier New",7)).pack(pady=(8,4))

    def _toggle(self):
        if self.hm.running:
            self.hm.stop()
            self._btn_var.set("▶  Start Hand Mouse")
            self._btn.config(bg=self.AC2)
        else:
            ok = self.hm.start()
            if ok:
                self._btn_var.set("⏹  Stop Hand Mouse")
                self._btn.config(bg=self.RD)

    def _on_notify(self, event, data=None):
        if event == "hand_status":
            self.win.after(0, lambda: self._status_var.set(data))
            if "active" in str(data):
                self.win.after(0, lambda: self._status_var.configure(fg=self.GR) if hasattr(self._status_var,'configure') else None)


if __name__ == "__main__":
    # Standalone test
    ui = HandMouseUI()
    ui.win.mainloop()
