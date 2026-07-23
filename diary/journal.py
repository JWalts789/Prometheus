"""Hash-chained, append-only diary — PROMETHEUS's tamper-evident autobiography.

Single-user Windows: direct file append (no cross-user socket like the Mac plan).
Guarantee: H_n = SHA256(H_{n-1} || canonical_json({seq,ts,prev,entry})). Any edit to
a past entry breaks the chain and verify() catches it. This is guardrail (g): the
loop can PROPOSE history, never silently REWRITE it.
"""
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

GENESIS = "0" * 64


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Diary:
    def __init__(self, path, publisher=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.publisher = publisher  # optional callable(record) -> called after each append
        self.head, self.seq = self._load()

    def _load(self):
        head, seq = GENESIS, 0
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        head = json.loads(line)["hash"]
                        seq += 1
        return head, seq

    def append(self, kind, **fields):
        core = {
            "seq": self.seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "prev": self.head,
            "entry": dict(kind=kind, **fields),
        }
        h = hashlib.sha256((self.head + _canon(core)).encode("utf-8")).hexdigest()
        rec = dict(core, hash=h)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(_canon(rec) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.head = h
        self.seq += 1
        if self.publisher is not None:
            try:
                self.publisher(rec)
            except Exception:
                pass  # a failed publish must never break the journal
        return rec

    def verify(self):
        """Return (ok, n_entries_or_break_line)."""
        prev, seq = GENESIS, 0
        if not self.path.exists():
            return True, 0
        with open(self.path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                core = {"seq": rec["seq"], "ts": rec["ts"], "prev": rec["prev"], "entry": rec["entry"]}
                h = hashlib.sha256((prev + _canon(core)).encode("utf-8")).hexdigest()
                if rec.get("prev") != prev or rec.get("seq") != seq or rec.get("hash") != h:
                    return False, lineno
                prev = h
                seq += 1
        return True, seq


if __name__ == "__main__":
    # self-test
    import tempfile
    p = Path(tempfile.gettempdir()) / "prom_diary_selftest.jsonl"
    if p.exists():
        p.unlink()
    d = Diary(p)
    d.append("boot", note="hello")
    d.append("wonder", q="why do I persist?")
    d.append("reflect", ok=False, note="unicode é ✓")
    print("verify clean:", d.verify())
    # tamper
    lines = p.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1]); rec["entry"]["q"] = "TAMPERED"
    lines[1] = _canon(rec)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("verify tampered:", Diary(p).verify())
    p.unlink()
