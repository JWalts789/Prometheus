"""Operator-directed curriculum.

The owner queues subjects from Discord (`!learn <topic>`). Each cycle studies the active
subject. For a newly-requested subject the narrator writes a FROZEN study set (source
facts) + a held-out probe, saved per-subject so the growth curve is measured against a
fixed test. Falls back to the default Ashfell if nothing is queued (or generation fails).
"""
import re
import json

import config
from sources.wikipedia import fetch_real_text

CUR_DIR = config.CURRICULUM_DIR
STATE = CUR_DIR / "state.json"

# Neutral fallback subject, used only if nothing is queued/current (rare in explore mode).
DEFAULT_SLUG = "foundations"
DEFAULT_NAME = "clear reasoning and broad general knowledge"


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "topic")[:40]


def _load():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8-sig"))  # tolerate a BOM
    return {"current": None, "queue": [], "subjects": {}}


def _save(s):
    CUR_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def enqueue(name):
    name = name.strip()
    s = _load()
    s["queue"].append({"slug": _slug(name), "name": name})
    _save(s)
    return name


def status():
    s = _load()
    cur = s.get("current")
    cur_name = (s["subjects"].get(cur, {}).get("name", cur) if cur else "nothing settled yet")
    return {"current": cur_name, "queue": [q["name"] for q in s["queue"]]}


def recent_names(n=8):
    s = _load()
    return [v.get("name", "") for v in list(s.get("subjects", {}).values())][-n:]


def current_source_summary(max_chars=600):
    """First ~max_chars of the current subject's REAL cached Wikipedia text (to ground chat),
    or '' if the subject was invented / never grounded."""
    cur = _load().get("current")
    if not cur:
        return ""
    p = CUR_DIR / cur / "source_text.md"
    if not p.exists():
        return ""
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return ""
    body = "\n".join(l for l in text.splitlines() if not l.strip().startswith("# ")).strip()
    return body[:max_chars]


_PROPOSE_PROMPT = """You are PROMETHEUS, a young AI that grows by studying REAL knowledge.
Propose ONE specific, REAL subject you are genuinely curious to learn next — for example a
field of science, a period of history, a technology, a craft, a real place, a language, a
natural phenomenon, a branch of mathematics, an economic idea, or a school of philosophy.
It MUST be real. Do NOT invent fictional worlds, realms, creatures, maps, or lore of any kind.
Make it specific and bounded enough to study in depth.
{hint}{avoid}
Reply with ONLY the subject as a short phrase — no explanation, no quotes."""


def propose(ollama, avoid=None, self_hint=None):
    """PROMETHEUS names a subject it wants to learn next (self-directed goal).

    `self_hint` (from its self-model's "what I'm drawn to") gently biases the choice toward
    its own evolving curiosity, without overriding the real-subjects-only rule."""
    avoid = [a for a in (avoid or []) if a]
    av = ("Do not repeat subjects you've recently studied: " + "; ".join(avoid) + ".") if avoid else ""
    hint = (f"Right now you find yourself drawn to: {self_hint.strip()}. Let that pull steer "
            "what you pick, while keeping it specific and real. ") if (self_hint or "").strip() else ""
    raw = ollama.chat(
        config.NARRATOR_MODEL,
        [{"role": "user", "content": _PROPOSE_PROMPT.format(hint=hint, avoid=av)}],
        options={"temperature": 1.0, "num_predict": 40},
    ).strip()
    line = (raw.splitlines()[0] if raw.splitlines() else "").strip().strip('"\'*` ').strip()
    line = re.sub(r"^(i\s+(would|will|think i|want to|would like to|choose to|shall)\s+"
                  r"(like to\s+)?(study|learn|explore|examine)(\s+about)?[:\-]?\s*)", "", line, flags=re.I)
    return (line[:120] or "the tardigrade, a microscopic survivor")


def _paths(slug):
    d = CUR_DIR / slug
    return d / "source_facts.md", d / "frozen_probe.jsonl"


_FACTS_PROMPT = """You are creating a compact study set about the REAL subject: "{topic}".
Write 14-18 concise, concrete, TRUE, factual statements about it that a student could learn —
real, accurate information only. Do NOT invent fictional lore, names, dates, or entities.
Put each fact on its own line, prefixed with "- ". Facts only, no preamble or numbering."""

_PROBE_PROMPT = """Using ONLY these facts, write 20 short question-and-answer pairs that test recall.
Rules for each answer:
- Keep it SHORT: one concept, ideally 1-4 words (a name, term, number, or brief phrase).
- Put the ONE canonical answer in "a". Do NOT bundle alternatives with slashes or parentheses.
- If it's commonly phrased other ways, list those wordings in "aliases" (otherwise []).
Vary the question phrasing. Output ONLY a JSON array like
[{{"q": "...", "a": "...", "aliases": ["..."]}}, {{"q": "...", "a": "...", "aliases": []}}].

FACTS:
{facts}"""


def _gen_facts(ollama, topic):
    raw = ollama.chat(
        config.NARRATOR_MODEL,
        [{"role": "user", "content": _FACTS_PROMPT.format(topic=topic)}],
        options={"temperature": 0.7, "num_predict": 800},
    )
    lines = [l.rstrip() for l in raw.splitlines() if l.strip().startswith("- ")]
    if not lines:  # narrator didn't bullet them — coerce
        lines = [f"- {l.strip()}" for l in raw.splitlines() if l.strip()][:18]
    return "\n".join(lines)


_DISTILL_PROMPT = """Below is a real, factual encyclopedia article about "{topic}".
Using ONLY information stated in this text, write 14-18 concise, concrete factual
statements a student could memorize. Copy the facts faithfully; do NOT add anything not
present in the text, and do NOT invent names, dates, or numbers.
Put each fact on its own line, prefixed with "- ". Facts only, no preamble or numbering.

ARTICLE:
{text}"""


def _distill_facts(ollama, topic, text):
    """GROUND a study set in REAL text: summarize the article into '- ' bullets, faithfully.
    Low temperature keeps it close to the source; falls back to invented facts if it yields none."""
    raw = ollama.chat(
        config.NARRATOR_MODEL,
        [{"role": "user", "content": _DISTILL_PROMPT.format(topic=topic, text=text)}],
        options={"temperature": 0.2, "num_predict": 800},
    )
    lines = [l.rstrip() for l in raw.splitlines() if l.strip().startswith("- ")]
    return "\n".join(lines) if lines else _gen_facts(ollama, topic)


def _gen_probe(ollama, facts):
    raw = ollama.chat(
        config.NARRATOR_MODEL,
        [{"role": "user", "content": _PROBE_PROMPT.format(facts=facts)}],
        options={"temperature": 0.6, "num_predict": 1600},
    )
    items = []
    m = re.search(r"\[.*\]", raw, re.S)
    if m:
        try:
            for o in json.loads(m.group(0)):
                if isinstance(o, dict) and o.get("q") and o.get("a"):
                    al = o.get("aliases") or []
                    al = [str(x).strip() for x in al if str(x).strip()] if isinstance(al, list) else []
                    items.append({"q": str(o["q"]).strip(), "a": str(o["a"]).strip(), "aliases": al})
        except Exception:
            pass
    if not items:
        for mo in re.finditer(r'\{[^{}]*"q"\s*:\s*"([^"]+)"[^{}]*"a"\s*:\s*"([^"]+)"[^{}]*\}', raw, re.S):
            items.append({"q": mo.group(1).strip(), "a": mo.group(2).strip(), "aliases": []})
    return items


def set_explore(on):
    s = _load()
    s["explore"] = bool(on)
    _save(s)
    return s["explore"]


def is_explore():
    return bool(_load().get("explore", False))


def record_result(slug, promoted, score=None):
    """Record whether the last cycle on `slug` improved (drives plateau detection), and track
    the best recall ever seen on it so goal-choice can steer away from low-ceiling subjects."""
    s = _load()
    subj = s["subjects"].setdefault(slug, {"name": slug})
    subj["cycles"] = subj.get("cycles", 0) + 1
    subj["last_promoted"] = bool(promoted)
    if score is not None:
        subj["best_new"] = max(subj.get("best_new", 0.0), float(score))
    _save(s)


def _source_text_path(slug):
    return CUR_DIR / slug / "source_text.md"


def _source_of(slug):
    """The Wikipedia article a subject was grounded in (from its source_facts header), or None."""
    facts_p, _ = _paths(slug)
    if not facts_p.exists():
        return None
    try:
        m = re.search(r"<!-- source: Wikipedia — (.+?) -->", facts_p.read_text(encoding="utf-8")[:400])
    except Exception:
        return None
    return m.group(1).strip() if m else None


def _ensure_subject(slug, name, ollama):
    """Ensure a frozen study set + probe exist for this subject. True on success.

    Grounds the study set in a real Wikipedia article when one exists (facts distilled
    from real text, raw article cached to source_text.md); otherwise falls back to
    narrator-invented facts (fictional subjects / offline). Either path yields the same
    output shape (- bullets + probe jsonl), so training/eval are unchanged."""
    facts_p, probe_p = _paths(slug)
    if facts_p.exists() and probe_p.exists():
        return True
    (CUR_DIR / slug).mkdir(parents=True, exist_ok=True)

    real = fetch_real_text(name)                   # (title, text) | None
    if real:
        title, text = real
        facts = _distill_facts(ollama, name, text)
        header = f"# {name}\n\n<!-- source: Wikipedia — {title} -->\n"
        _source_text_path(slug).write_text(f"# {title}\n\n{text}\n", encoding="utf-8")
    else:                                          # made-up subject / offline / no match
        facts = _gen_facts(ollama, name)
        header = f"# {name}\n\n"

    probe = _gen_probe(ollama, facts)
    if len(probe) < 5:  # couldn't build a fair test -> don't switch to it
        return False
    facts_p.write_text(header + facts + "\n", encoding="utf-8")
    with open(probe_p, "w", encoding="utf-8") as f:
        for it in probe:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return True


def reground(name):
    """Clear a subject's cached study material so its NEXT study re-ingests from real text.
    Returns (slug, files_removed). Safe on a never-studied subject (removes nothing)."""
    slug = _slug(name)
    facts_p, probe_p = _paths(slug)
    removed = 0
    for p in (facts_p, probe_p, _source_text_path(slug)):
        try:
            if p.exists():
                p.unlink()
                removed += 1
        except Exception:
            pass
    return slug, removed


def _default_subject(ollama):
    """Neutral fallback subject (only when nothing else is queued/current)."""
    _ensure_subject(DEFAULT_SLUG, DEFAULT_NAME, ollama)
    facts_p, probe_p = _paths(DEFAULT_SLUG)
    return {"slug": DEFAULT_SLUG, "name": DEFAULT_NAME,
            "facts_path": str(facts_p), "probe_path": str(probe_p), "fresh": None,
            "source": _source_of(DEFAULT_SLUG)}


MAX_CYCLES_PER_SUBJECT = 3


def activate_next(ollama):
    """Pick the subject to study this cycle -> {slug,name,facts_path,probe_path,fresh}.

    Priority: (1) an owner-queued subject; (2) in explore mode, a self-proposed new subject
    once the current one has plateaued; (3) otherwise continue current / the Ashfell.
    """
    s = _load()
    fresh = None
    chosen = None

    if s["queue"]:
        nxt = s["queue"].pop(0)
        chosen = (nxt["slug"], nxt["name"])
    elif s.get("explore"):
        cur = s.get("current")
        subj = s["subjects"].get(cur, {}) if cur else {}
        plateaued = (not cur) or (subj.get("last_promoted") is False) or (subj.get("cycles", 0) >= MAX_CYCLES_PER_SUBJECT)
        if plateaued:
            existing = set(s.get("subjects", {}).keys())
            self_hint = None
            try:  # let the evolving self-model's curiosity steer the choice (lazy import: no cycle)
                import self_model
                self_hint = self_model.drawn_to()
            except Exception:
                pass
            name = None
            for _ in range(4):  # keep proposing until it's a genuinely NEW subject (no rut on old slugs)
                cand = propose(ollama, avoid=recent_names(), self_hint=self_hint)
                if _slug(cand) not in existing:
                    name = cand
                    break
            if name:
                chosen = (_slug(name), name)

    if chosen:
        slug, name = chosen
        if _ensure_subject(slug, name, ollama):
            s["current"] = slug
            subj = s["subjects"].setdefault(slug, {})
            subj["name"] = name
            subj.setdefault("cycles", 0)
            fresh = name
        _save(s)

    cur = s.get("current")
    if cur:
        facts_p, probe_p = _paths(cur)
        if facts_p.exists() and probe_p.exists():
            return {"slug": cur, "name": s["subjects"].get(cur, {}).get("name", cur),
                    "facts_path": str(facts_p), "probe_path": str(probe_p),
                    "fresh": fresh, "source": _source_of(cur)}
    return _default_subject(ollama)
