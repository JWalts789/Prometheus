"""Print PROMETHEUS's capability curve from the hash-chained diary."""
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config


def _rows():
    rows = {}
    with open(config.DIARY_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)["entry"]
            c = e.get("cycle")
            if c is None:
                continue
            r = rows.setdefault(c, {})
            if e["kind"] == "baseline_eval":
                r["before"], r["before_ret"] = e["new"], e["retain"]
            elif e["kind"] == "trained_eval":
                r["after"], r["after_ret"] = e["new"], e["retain"]
            elif e["kind"] == "gate":
                r["accepted"] = e["accept"]
    return rows


def print_curve():
    rows = _rows()
    print("\n  PROMETHEUS — Ashfell capability curve (held-out probe)")
    print("  cycle | best-before -> after  (retain)      | result   bar(after)")
    print("  ------+--------------------------------------+---------------------")
    best = 0.0
    for c in sorted(rows):
        r = rows[c]
        after = r.get("after", 0.0)
        bar = "#" * round(after * 20)
        promo = "PROMOTED" if r.get("accepted") else "rejected"
        print(f"   {c:>3}  | {r.get('before',0):>4.0%} -> {after:>4.0%}  "
              f"(ret {r.get('before_ret',0):.0%}->{r.get('after_ret',0):.0%}) | {promo:<8} {bar}")
        if r.get("accepted"):
            best = after
    try:
        st = json.loads(config.STATE_JSON.read_text(encoding="utf-8"))
        print(f"\n  current best (promoted): probe {st['prev_new']:.0%}, retain {st['prev_retain']:.0%} "
              f"-> {st['promoted_adapter']}")
    except Exception:
        pass


if __name__ == "__main__":
    print_curve()
