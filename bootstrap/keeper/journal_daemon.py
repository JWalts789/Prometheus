#!/usr/bin/env python3
"""PROMETHEUS Keeper — hash-chained, append-only journal daemon.

Runs as the `keeper` user. Listens on a Unix socket that the `prom` (agent) user
may WRITE to but cannot use to rewrite history. For each request (one JSON object
per line) it computes:

    H_n = SHA256( H_{n-1} || canonical_json({seq, ts, prev, entry}) )

appends {seq, ts, prev, entry, hash} to the canonical JSONL under ~keeper, persists
the new head hash, and returns {ok, seq, hash}. The canonical file and the head hash
live where `prom` cannot read or write them. This is guardrail (g): the agent can
PROPOSE history but never REWRITE it — any tamper breaks the chain (see verify_chain.py).

Stdlib only. Start as keeper:
    python3 journal_daemon.py
"""
import os
import sys
import json
import time
import socket
import hashlib
import threading

HOME = os.path.expanduser("~")                              # /Users/keeper when run as keeper
JOURNAL_DIR = os.path.join(HOME, "prometheus")
JOURNAL_FILE = os.path.join(JOURNAL_DIR, "journal.jsonl")
HEAD_FILE = os.path.join(JOURNAL_DIR, "journal.head")
SOCKET_PATH = "/Users/Shared/prometheus/journal.sock"      # cross-user append entrypoint
GENESIS = "0" * 64
MAX_ENTRY_BYTES = 1_000_000

_lock = threading.Lock()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _load_head() -> str:
    if os.path.exists(HEAD_FILE):
        with open(HEAD_FILE) as f:
            h = f.read().strip()
            if h:
                return h
    # fall back to recomputing from the last record if the head file is missing
    if os.path.exists(JOURNAL_FILE):
        last = None
        with open(JOURNAL_FILE, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line.strip()
        if last:
            return json.loads(last)["hash"]
    return GENESIS


def _count_entries() -> int:
    if not os.path.exists(JOURNAL_FILE):
        return 0
    n = 0
    with open(JOURNAL_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


class Journal:
    def __init__(self):
        os.makedirs(JOURNAL_DIR, exist_ok=True)
        os.chmod(JOURNAL_DIR, 0o700)
        self.head = _load_head()
        self.seq = _count_entries()

    def append(self, entry):
        with _lock:
            core = {"seq": self.seq, "ts": time.time(), "prev": self.head, "entry": entry}
            h = hashlib.sha256((self.head + canonical(core)).encode("utf-8")).hexdigest()
            record = dict(core, hash=h)
            with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
                f.write(canonical(record) + "\n")
                f.flush()
                os.fsync(f.fileno())
            tmp = HEAD_FILE + ".tmp"
            with open(tmp, "w") as f:
                f.write(h)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, HEAD_FILE)
            self.head = h
            self.seq += 1
            return {"ok": True, "seq": record["seq"], "hash": h}


def _handle(conn, journal):
    try:
        conn.settimeout(5)
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX_ENTRY_BYTES:
                raise ValueError("entry too large")
        line = buf.split(b"\n", 1)[0].decode("utf-8").strip()
        if not line:
            raise ValueError("empty request")
        resp = journal.append(json.loads(line))
    except Exception as e:  # noqa: BLE001 — report, never crash the daemon
        resp = {"ok": False, "error": str(e)}
    try:
        conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
    finally:
        conn.close()


def serve():
    os.makedirs(os.path.dirname(SOCKET_PATH), exist_ok=True)
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass
    journal = Journal()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCKET_PATH)
    # prom may connect & append; APPEND is the only operation the socket exposes.
    os.chmod(SOCKET_PATH, 0o666)
    srv.listen(64)
    print(f"[keeper] journal daemon listening on {SOCKET_PATH}", flush=True)
    print(f"[keeper] canonical journal: {JOURNAL_FILE}  (head {journal.head[:12]}...)", flush=True)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=_handle, args=(conn, journal), daemon=True).start()


if __name__ == "__main__":
    try:
        serve()
    except KeyboardInterrupt:
        sys.exit(0)
