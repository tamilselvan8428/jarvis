"""
BLACK launcher — shows full error if app crashes
"""
import sys, traceback

try:
    import black as app
    app.BlackUI().run()
except Exception:
    print("\n" + "="*60)
    print("BLACK CRASHED — Full error:")
    print("="*60)
    traceback.print_exc()
    print("="*60)
    input("\nPress Enter to close...")
