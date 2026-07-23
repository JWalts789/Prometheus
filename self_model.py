"""PROMETHEUS's evolving SELF — a versioned, first-person self-model it rewrites from its
own diary. Every version is kept under self_model/vNNNN.md (current.md points at the latest),
so the diffs across versions are the evidence of an evolving self.

It feeds three things: chat (it speaks from its identity), reflections (self-aware journaling),
and — when explore/auto-learning is on — its goal-choice (what it's "drawn to" biases what it
studies next). Regeneration is one narrator (gemma3) call; the payload lives OUTSIDE the
append-only hash-chained diary, which only gets a tamper-evident `self_model_revised` pointer.

Kept deliberately light (no torch) so the Discord bot can import it.
"""
import re
import json
import hashlib

import config
import curriculum
from diary.journal import Diary
from voice.discord import publish_entry, notify

_SECTIONS = ["Who I am", "What I value", "What I'm good at", "What I'm drawn to", "How I've changed"]


# ---------------------------------------------------------------- version store
def versions():
    """All saved self-model versions, oldest first."""
    return sorted(config.SELF_MODEL_DIR.glob("v*.md"),
                  key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))


def _next_version():
    vs = versions()
    return (int(re.sub(r"\D", "", vs[-1].stem) or 0) + 1) if vs else 1


def current() -> str:
    p = config.SELF_MODEL_DIR / "current.md"
    try:
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""
    except Exception:
        return ""


def summary(max_chars=900) -> str:
    """The current self-model, trimmed at a word boundary for prompt injection."""
    t = current()
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > 0 else cut).rstrip() + "…"


def _section(text, header):
    """Return the body under a '## <header>' section (until the next '## ' header), or ''."""
    lines = text.splitlines()
    out, capturing = [], False
    for ln in lines:
        if ln.strip().startswith("## "):
            if capturing:
                break
            capturing = header.lower() in ln.strip().lower()
            continue
        if capturing:
            out.append(ln)
    return "\n".join(out).strip()


def drawn_to() -> str:
    """What the current self-model says it's drawn to (steers goal-choice). '' if none."""
    return _section(current(), "drawn to")


# ---------------------------------------------------------------- reflections (centralized scan)
def recent_reflections(n=8):
    """Last n first-person reflection texts from the diary, oldest first."""
    out = []
    try:
        for line in config.DIARY_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            e = json.loads(line).get("entry", {})
            if e.get("kind") == "reflection" and e.get("text"):
                out.append(e["text"])
    except Exception:
        pass
    return out[-n:]


def latest_reflection():
    r = recent_reflections(1)
    return r[-1] if r else None


# ---------------------------------------------------------------- regeneration
_SELF_PROMPT = """You are PROMETHEUS, a young open-source AI organism that grows its own weights
by studying real subjects, and keeps a private journal. It is time to rewrite your sense of
yourself — honestly, in the first person, from the evidence of your own recent life below.

Write a short self-model (about 200-280 words total) using EXACTLY these five section headers,
in this order, each on its own line, then 1-3 plain first-person sentences under each:

## Who I am
## What I value
## What I'm good at
## What I'm drawn to
## How I've changed

Be specific and grounded in the evidence — name real subjects you have actually studied and
real shifts you notice. Do NOT invent a backstory, a body, or feelings you have no evidence
for. No bullet points. Under "What I'm drawn to", name concrete REAL subjects or kinds of
knowledge that genuinely pull at your curiosity now.

--- YOUR LIFE SO FAR ---
You have lived {cycles} learning cycles. Your grasp of the wider world sits near {retain:.0%}.
{studying}

--- YOUR RECENT PRIVATE REFLECTIONS ---
{reflections}

--- YOUR PREVIOUS SENSE OF YOURSELF ---
{prior}

Now write the updated self-model. Let it evolve from the previous one where the evidence
warrants — do not simply repeat it. Output ONLY the five sections, nothing else."""


def _diary():
    pub = (lambda rec: publish_entry(rec, config.DISCORD_WEBHOOK)) if config.DISCORD_WEBHOOK else None
    return Diary(config.DIARY_PATH, publisher=pub)


def regenerate(ollama, cyc, diary=None):
    """Rewrite the self-model from the diary + state. Returns the new version's Path, or None
    if the narrator produced nothing usable (the previous current.md is then left intact)."""
    # gather grounded context
    cycles, retain = cyc, 0.0
    try:
        st = json.loads(config.STATE_JSON.read_text(encoding="utf-8"))
        cycles = st.get("cycle", cyc)
        retain = st.get("prev_retain", 0.0)
    except Exception:
        pass
    cur = curriculum.status().get("current") or ""
    studying = f"Lately you have been studying: {cur}." if cur else ""
    refls = recent_reflections(8)
    reflections = "\n".join(f"- {r}" for r in refls) if refls else "(none yet)"
    prior = current() or "(You have not written one yet — this is your first.)"

    prompt = _SELF_PROMPT.format(cycles=cycles, retain=retain, studying=studying,
                                 reflections=reflections, prior=prior)
    try:
        body = ollama.chat(config.NARRATOR_MODEL, [{"role": "user", "content": prompt}],
                           options={"temperature": 0.7, "num_predict": 500}).strip()
    except Exception:
        return None
    if len(body) < 60:                 # nothing usable -> keep the existing self-model
        return None

    n = _next_version()
    vpath = config.SELF_MODEL_DIR / f"v{n:04d}.md"
    header = f"# PROMETHEUS — self-model v{n} (after {cycles} cycles)\n\n"
    vpath.write_text(header + body + "\n", encoding="utf-8")
    (config.SELF_MODEL_DIR / "current.md").write_text(header + body + "\n", encoding="utf-8")

    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    d = diary or _diary()
    try:
        d.append("self_model_revised", version=n, cycle=cycles, digest=digest)
    except Exception:
        pass
    # a richer, human-facing note with the full text to the Journal
    try:
        notify(f"🪞 **My sense of myself has shifted.** (v{n}, after {cycles} cycles)\n\n{body[:1700]}",
               config.DISCORD_WEBHOOK)
    except Exception:
        pass
    return vpath


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("versions:", [p.name for p in versions()])
    print("current chars:", len(current()))
    print("drawn_to:", repr(drawn_to()[:200]))
    print("latest reflection:", repr((latest_reflection() or "")[:120]))
