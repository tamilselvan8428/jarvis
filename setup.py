#!/usr/bin/env python3
"""
BLACK Setup Script
Run this once before launching black.py
"""
import subprocess, sys, platform, os

OS = platform.system()

def run(cmd, shell=False):
    print(f"  → {' '.join(cmd) if isinstance(cmd,list) else cmd}")
    subprocess.run(cmd, shell=shell, check=False)

print("=" * 55)
print("  BLACK Setup")
print("=" * 55)

# 1. System deps
if OS == "Linux":
    print("\n[1/3] Installing system packages...")
    run("sudo apt-get update -qq", shell=True)
    run("sudo apt-get install -y portaudio19-dev python3-tk python3-dev espeak", shell=True)
elif OS == "Darwin":
    print("\n[1/3] Installing system packages (Homebrew)...")
    run(["brew", "install", "portaudio"])
elif OS == "Windows":
    print("\n[1/3] Windows detected — install PortAudio manually if mic doesn't work.")
    print("  Download: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio")

# 2. Python deps
print("\n[2/3] Installing Python packages...")
pip = [sys.executable, "-m", "pip", "install", "--break-system-packages"]
packages = [
    "google-generativeai",
    "SpeechRecognition",
    "pyttsx3",
    "Pillow",
    "pyautogui",
    "psutil",
]
try:
    run(pip + ["pyaudio"])
except Exception:
    print("  ⚠  PyAudio failed — mic won't work, but text input still works.")

for pkg in packages:
    run(pip + [pkg])

# 3. API key
print("\n[3/3] API Key Setup")
print("  Get your key at: https://aistudio.google.com/apikey")
key = input("  Paste your Gemini API key (or press Enter to skip): ").strip()
if key:
    env_line = f'\nexport GEMINI_API_KEY="{key}"\n'
    # Write to shell rc
    for rc in ["~/.bashrc", "~/.zshrc"]:
        try:
            with open(os.path.expanduser(rc), "a") as f:
                f.write(env_line)
            print(f"  ✓ Key saved to {rc}")
            break
        except Exception:
            pass
    # Also write to .env for direct loading
    with open(os.path.join(os.path.dirname(__file__), ".env"), "w") as f:
        f.write(f'GEMINI_API_KEY={key}\n')
    print("  ✓ Key saved to .env")
    os.environ["GEMINI_API_KEY"] = key

print("\n✅ Setup complete!")
print("   Launch BLACK with:  python3 black.py")
print("=" * 55)
