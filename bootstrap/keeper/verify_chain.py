#!/usr/bin/env python3
"""Independent verifier for the PROMETHEUS hash-chained journal.

Recomputes the whole chain from genesis and confirms every link. Run by the Keeper
(from the kill-switch watchdog and/or a launchd timer). Exit 0 = intact; exit 1 =
tamper detected -> break the glass (kill switch). Must stay byte-for-byte consistent
with journal_daemon.py's hashing.
"""
import os
import sys
import json
import hashlib

HOME = os.path.expanduser("~")
JOURNAL_FILE = os.path.join(HOME, "prometheus", "journal.jsonl")
GENESIS = "0" * 64


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    if not os.path.exists(JOURNAL_FILE):
        print("no journal yet — OK")
        return 0
    prev = GENESIS
    seq = 0
    with open(JOURNAL_FILE, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("prev") != prev:
                print(f"BREAK at line {lineno}: prev-hash mismatch")
                return 1
            if rec.get("seq") != seq:
                print(f"BREAK at line {lineno}: seq mismatch (got {rec.get('seq')}, expected {seq})")
                return 1
            core = {"seq": rec["seq"], "ts": rec["ts"], "prev": rec["prev"], "entry": rec["entry"]}
            h = hashlib.sha256((prev + canonical(core)).encode("utf-8")).hexdigest()
            if h != rec.get("hash"):
                print(f"BREAK at line {lineno}: hash mismatch — entry {seq} was altered")
                return 1
            prev = h
            seq += 1
    print(f"OK — {seq} entries, head {prev[:12]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
