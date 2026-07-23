"""Repair the diary by truncating to its longest hash-valid prefix.

Concurrency (multiple writers) can corrupt the tail of the chain. This keeps every
entry up to the first break, backs up the original, and rewrites the clean prefix so
the chain verifies again. It never rewrites/relaunders past entries (that would defeat
tamper-evidence) — it only drops the unverifiable tail.
"""
import sys
import json
import shutil
import hashlib
from pathlib import Path

import config

GENESIS = "0" * 64


def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def longest_valid_prefix(path):
    prev, seq, valid = GENESIS, 0, []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            break
        core = {"seq": rec.get("seq"), "ts": rec.get("ts"), "prev": rec.get("prev"), "entry": rec.get("entry")}
        h = hashlib.sha256((prev + _canon(core)).encode("utf-8")).hexdigest()
        if rec.get("prev") != prev or rec.get("seq") != seq or rec.get("hash") != h:
            break
        valid.append(line)
        prev, seq = h, seq + 1
    return valid


if __name__ == "__main__":
    p = config.DIARY_PATH
    if not p.exists():
        print("no diary; nothing to repair")
        sys.exit(0)
    total = sum(1 for line in open(p, encoding="utf-8") if line.strip())
    valid = longest_valid_prefix(p)
    if len(valid) == total:
        print(f"diary already fully valid ({total} entries)")
        sys.exit(0)
    bak = str(p) + ".corrupt.bak"
    shutil.copy(p, bak)
    p.write_text("\n".join(valid) + ("\n" if valid else ""), encoding="utf-8")
    print(f"repaired: kept {len(valid)}/{total} valid entries; corrupted original -> {bak}")
