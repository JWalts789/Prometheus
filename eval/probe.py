"""Frozen-probe evaluator + promotion gate.

Decoupled from any model: pass a `generate(prompt) -> str` callable. Two probe sets:
  NEW    (the invented domain) -> measures GAIN
  RETAIN (general knowledge)   -> measures FORGETTING
Grading is deterministic (normalized whole-word / number-word match) so the capability
curve is objective — no LLM judge to game.
"""
import re
import json
from pathlib import Path

_NUMWORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
             "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten"}


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are", "was",
         "were", "with", "as", "by", "at", "its", "it", "that", "this", "these", "those",
         "from", "be", "been", "being", "which", "who", "whom", "into", "than", "then", "s"}


def _stem(t: str) -> str:
    """Crude, order-stable fold so morphological variants match: plural 's' first, then
    'ing'/'ed'. 'photos'->'photo', 'prompting'/'prompts'->'prompt', 'setting'/'settings'->'sett'.
    Length-guarded so short words ('king','thing','red') are left intact."""
    if len(t) > 3 and t.endswith("s"):
        t = t[:-1]
    for suf in ("ing", "ed"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[:-len(suf)]
    return t


# bare yes/no words must never become standalone matchers (splitting "Yes, because X" on the
# comma would otherwise let "yes" match any affirmative answer regardless of the reasoning).
_AFFIRM = {"yes", "no", "true", "false", "none", "maybe", "na", "n a", "nan", "not"}


def _variants(answer: str):
    """Expand a gold answer into acceptable variants so a correct-but-partial answer isn't
    scored wrong: the full string, each '/'|','|';' segment, the parenthetical-stripped form,
    and each parenthetical's content. Turns bundled golds like 'Specific styles/settings' or
    "Christie's (New York)" into an alias set. Bare affirmations from SEGMENTS are dropped so
    'Yes, through gene changes' doesn't match every 'Yes ...' answer (the full string is kept)."""
    a = (answer or "").strip()
    if not a:
        return set()
    out = {a}
    for p in re.findall(r"\(([^)]*)\)", a):          # parenthetical contents
        out.add(p)
    stripped = re.sub(r"\([^)]*\)", " ", a)          # paren-stripped
    out.add(stripped)
    for seg in re.split(r"[/,;]", stripped):         # alternative segments
        seg = seg.strip()
        if seg and _norm(seg) not in _AFFIRM:        # don't let 'Yes'/'No' segments match
            out.add(seg)
    return {v.strip() for v in out if v.strip()}


def _numword_hit(nv: str, o: str) -> bool:
    if nv in _NUMWORDS and re.search(r"\b" + _NUMWORDS[nv] + r"\b", o):
        return True
    for digit, word in _NUMWORDS.items():
        if nv == word and re.search(r"\b" + re.escape(digit) + r"\b", o):
            return True
    return False


def _match(output: str, answers) -> bool:
    o = _norm(output)
    otoks = {_stem(t) for t in o.split()}
    for a in answers:
        for v in _variants(a):
            nv = _norm(v)
            if not nv:
                continue
            # 1) exact contiguous phrase (strongest signal)
            if re.search(r"\b" + re.escape(nv) + r"\b", o):
                return True
            # 2) number-word / digit equivalence
            if _numword_hit(nv, o):
                return True
            # 3) content-token overlap (order-free, plural-folded): all content words present,
            #    or >=60% of them for longer answers -> tolerant of reordering / partial phrasing
            gtoks = [_stem(t) for t in nv.split() if t not in _STOP]
            if gtoks:
                hit = sum(1 for t in gtoks if t in otoks)
                if hit == len(gtoks):
                    return True
                if len(gtoks) >= 3 and hit / len(gtoks) >= 0.6:
                    return True
    return False


def load_probe(path):
    items = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def score(generate, probe):
    """Return (accuracy, per-item results)."""
    correct, results = 0, []
    for it in probe:
        answers = [it["a"]] + it.get("aliases", [])
        out = generate(it["q"])
        ok = _match(out, answers)
        correct += int(ok)
        results.append({"q": it["q"], "expected": it["a"], "got": out.strip()[:120], "ok": ok})
    return (correct / len(probe) if probe else 0.0), results


def gate(new_score, retain_score, prev_new, prev_retain, retain_min, gain_min):
    """Accept a new adapter iff it strictly gains on NEW and doesn't forget on RETAIN."""
    retain_ok = True if prev_retain <= 0 else retain_score >= retain_min * prev_retain
    gain_ok = (new_score - prev_new) > gain_min
    detail = {"new": round(new_score, 4), "prev_new": round(prev_new, 4),
              "retain": round(retain_score, 4), "prev_retain": round(prev_retain, 4),
              "retain_ok": retain_ok, "gain_ok": gain_ok}
    return (retain_ok and gain_ok), detail


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    new_probe = load_probe(root / "probe" / "frozen_probe.jsonl")
    retain_probe = load_probe(root / "probe" / "retain_probe.jsonl")
    print(f"loaded NEW={len(new_probe)} RETAIN={len(retain_probe)}")

    # oracle generator: answers everything correctly -> validates grading is lenient enough
    oracle = {it["q"]: it["a"] for it in new_probe + retain_probe}
    acc_new, _ = score(lambda q: oracle[q], new_probe)
    acc_ret, _ = score(lambda q: oracle[q], retain_probe)
    print(f"oracle NEW acc={acc_new:.2f}  RETAIN acc={acc_ret:.2f}  (both should be 1.00)")

    # dunce generator: always says 'I do not know' -> should score ~0 on NEW
    acc_dunce, _ = score(lambda q: "I do not know.", new_probe)
    print(f"dunce NEW acc={acc_dunce:.2f}  (should be ~0.00)")

    # gate demo: went 0.05 -> 0.60 on NEW, retain held 0.90 -> 0.88
    print("gate demo:", gate(0.60, 0.88, 0.05, 0.90, retain_min=0.95, gain_min=0.0))
