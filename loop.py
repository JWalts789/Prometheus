"""PROMETHEUS always-on loop.

Runs a self-edit cycle on a schedule, forever, journaling to the hash-chained diary
and speaking to the private Discord channel. Kept alive across reboots by a Windows
Task Scheduler "at logon" task (see register_task.ps1). State (cycle counter, best
adapter) persists in state.json, so a restart resumes rather than restarts.
"""
import os
import sys
import time
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from apscheduler.schedulers.blocking import BlockingScheduler

import config
import lock
from cycle import run_cycle, _make_diary

INTERVAL_HOURS = float(os.environ.get("PROM_INTERVAL_HOURS", "6"))


def _tick():
    try:
        run_cycle()
    except Exception as e:  # a bad cycle must never kill the organism
        _make_diary().append("cycle_error", error=str(e))


def main():
    lock.acquire(lock.LOOP_LOCK)  # single loop instance; the training lock is taken per-cycle
    diary = _make_diary()
    ok, n = diary.verify()
    diary.append("loop_boot", interval_hours=INTERVAL_HOURS, diary_ok=ok, entries=n)

    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(
        _tick, "interval", hours=INTERVAL_HOURS,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=90),
        max_instances=1, coalesce=True, misfire_grace_time=3600,
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        _make_diary().append("loop_stop")


if __name__ == "__main__":
    main()
