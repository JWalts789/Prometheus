"""Run N self-edit cycles back-to-back (continual), then print the capability curve.
Usage: python run_cycles.py [N]   (default 4)
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from cycle import run_cycle
from curve import print_curve

n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
for i in range(n):
    print(f"\n===== batch cycle {i + 1}/{n} =====")
    try:
        run_cycle()
    except Exception as e:
        print(f"[batch] cycle failed: {e}")
        break

print_curve()
