"""Single-instance guard.

Two PROMETHEUS processes writing the diary at once corrupts the hash chain (each
computes its prev-hash from a stale head). This makes a second start refuse to run.
"""
import os
import sys
import atexit
from pathlib import Path

_DIR = Path(__file__).resolve().parent
LOCK = _DIR / "prometheus.lock"   # held ONLY while a cycle is actively training
BOT_LOCK = _DIR / "bot.lock"      # single Discord bot instance
LOOP_LOCK = _DIR / "loop.lock"    # single always-on loop instance (held for its whole life)


def _alive(pid):
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    except Exception:
        return False  # can't tell -> treat as dead so a stale lock never wedges us


def acquire(lockfile=LOCK):
    lockfile = Path(lockfile)
    if lockfile.exists():
        try:
            pid = int(lockfile.read_text().strip())
        except Exception:
            pid = None
        if pid and pid != os.getpid() and _alive(pid):
            print(f"[lock] Another instance holds {lockfile.name} (PID {pid}). "
                  "Refusing to start a second. Exiting.")
            sys.exit(3)
    lockfile.write_text(str(os.getpid()))
    atexit.register(lambda: release(lockfile))


def release(lockfile=LOCK):
    lockfile = Path(lockfile)
    try:
        if lockfile.exists() and lockfile.read_text().strip() == str(os.getpid()):
            lockfile.unlink()
    except Exception:
        pass


def is_held(lockfile=LOCK):
    """True if a LIVE process currently holds this lock."""
    lockfile = Path(lockfile)
    if not lockfile.exists():
        return False
    try:
        return _alive(int(lockfile.read_text().strip()))
    except Exception:
        return False


def try_acquire(lockfile=LOCK):
    """Non-fatal acquire: returns True if taken, False if a live other process holds it."""
    lockfile = Path(lockfile)
    if lockfile.exists():
        try:
            pid = int(lockfile.read_text().strip())
        except Exception:
            pid = None
        if pid and pid != os.getpid() and _alive(pid):
            return False
    lockfile.write_text(str(os.getpid()))
    return True
