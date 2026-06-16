"""
BLACK - Click Calibration Tool
Shows a target crosshair, user clicks it, measures offset, saves correction.
"""
import sys, ctypes
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import tkinter as tk
import json, os

CALIB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibration.json")

TEST_POINTS = [(0.25,0.25),(0.75,0.25),(0.50,0.50),(0.25,0.75),(0.75,0.75)]

class CalibrationTool:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BLACK Calibration")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="black")
        self.root.attributes("-alpha", 0.88)
        self.SW = self.root.winfo_screenwidth()
        self.SH = self.root.winfo_screenheight()
        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._click)
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.results = []
        self.idx = 0
        self.points = [(int(nx*self.SW), int(ny*self.SH)) for nx,ny in TEST_POINTS]
        self._draw(self.points[0])

    def _draw(self, pos):
        self.canvas.delete("all")
        x, y = pos
        self.canvas.create_rectangle(0,0,self.SW,self.SH, fill="black", stipple="gray25")
        self.canvas.create_text(self.SW//2, 40,
            text=f"Click EXACTLY on the crosshair centre  ({self.idx+1}/{len(self.points)})",
            fill="#00d4ff", font=("Courier New",18,"bold"))
        self.canvas.create_text(self.SW//2, 72,
            text="Press ESC to cancel",
            fill="#445566", font=("Courier New",12))
        self.canvas.create_oval(x-40,y-40,x+40,y+40, outline="#00d4ff", width=2)
        self.canvas.create_oval(x-15,y-15,x+15,y+15, outline="#ffff00", width=2)
        self.canvas.create_line(x-70,y,x+70,y, fill="#ff3333", width=2)
        self.canvas.create_line(x,y-70,x,y+70, fill="#ff3333", width=2)
        self.canvas.create_oval(x-5,y-5,x+5,y+5, fill="white")
        self.canvas.create_rectangle(x+18,y-26,x+145,y-8, fill="black", outline="#00d4ff")
        self.canvas.create_text(x+82, y-17, text=f"target ({x},{y})",
            fill="#ffff00", font=("Courier New",10))

    def _click(self, e):
        tx,ty = self.points[self.idx]
        dx,dy = e.x-tx, e.y-ty
        self.results.append({"target":(tx,ty),"clicked":(e.x,e.y),"error":(dx,dy)})
        print(f"[CAL] {self.idx+1}: target=({tx},{ty}) clicked=({e.x},{e.y}) err=({dx:+d},{dy:+d})")
        self.idx += 1
        if self.idx >= len(self.points):
            self._finish()
        else:
            self._draw(self.points[self.idx])

    def _finish(self):
        self.canvas.delete("all")
        avg_dx = sum(r["error"][0] for r in self.results)/len(self.results)
        avg_dy = sum(r["error"][1] for r in self.results)/len(self.results)
        corr_x, corr_y = -int(avg_dx), -int(avg_dy)
        calib = {"offset_x":corr_x,"offset_y":corr_y,
                 "avg_error_x":round(avg_dx,1),"avg_error_y":round(avg_dy,1),
                 "screen":[self.SW,self.SH]}
        with open(CALIB_FILE,"w") as f:
            json.dump(calib, f, indent=2)
        mx,my = self.SW//2, self.SH//2
        self.canvas.create_text(mx,my-60, text="✓ Calibration Complete",
            fill="#00ff88", font=("Courier New",24,"bold"))
        self.canvas.create_text(mx,my,
            text=f"Avg error:  X={avg_dx:+.1f}px   Y={avg_dy:+.1f}px",
            fill="#ffff00", font=("Courier New",14))
        self.canvas.create_text(mx,my+35,
            text=f"Correction saved:  X={corr_x:+d}   Y={corr_y:+d}",
            fill="#00d4ff", font=("Courier New",14))
        self.canvas.create_text(mx,my+70,
            text="BLACK will use this automatically. Click to close.",
            fill="#667788", font=("Courier New",11))
        self.canvas.bind("<Button-1>", lambda e: self.root.destroy())
        print(f"[CAL] Saved offset ({corr_x:+d},{corr_y:+d}) → {CALIB_FILE}")

    def run(self): self.root.mainloop()

def load_calibration():
    try:
        if os.path.exists(CALIB_FILE):
            d = json.load(open(CALIB_FILE))
            ox,oy = d.get("offset_x",0), d.get("offset_y",0)
            print(f"[CAL] offset=({ox:+d},{oy:+d})")
            return ox, oy
    except Exception as e:
        print(f"[CAL] {e}")
    return 0, 0

if __name__ == "__main__":
    CalibrationTool().run()
