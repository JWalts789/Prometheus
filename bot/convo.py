"""Conversation memory — so PROMETHEUS can actually know you across messages and days.

Two layers:
  * ROLLING per-channel history (in-process): the last ~12 turns, fed back as real multi-turn
    context so it remembers what was just said.
  * LONG-TERM per-user record (on disk, logs/conversations/<id>.json): name, when first met
    (cycle), message count, and a one-line 'what I remember about them' the narrator distills
    every few messages — so it can say 'last time you asked about honeybees'.
Kept light (json + gemma3 via the passed Ollama handle); no GPU of its own.
"""
import json
from collections import deque, defaultdict

import config

_CONVO_DIR = config.LOGS_DIR / "conversations"
_CONVO_DIR.mkdir(parents=True, exist_ok=True)

_MAX_TURNS = 12                                   # keep the last 12 exchanges (24 messages)
_history = defaultdict(lambda: deque(maxlen=_MAX_TURNS * 2))


# ---------------------------------------------------------------- rolling per-channel history
def record_user(channel_id, user_name, text):
    _history[channel_id].append({"role": "user", "name": user_name, "content": text})


def record_bot(channel_id, text):
    _history[channel_id].append({"role": "assistant", "name": "PROMETHEUS", "content": text})


def recent_turns(channel_id):
    """Prior turns as chat messages (user turns are name-prefixed so it can tell people apart)."""
    out = []
    for m in _history[channel_id]:
        if m["role"] == "user":
            out.append({"role": "user", "content": f'{m["name"]}: {m["content"]}'})
        else:
            out.append({"role": "assistant", "content": m["content"]})
    return out


# ---------------------------------------------------------------- long-term per-user record
def _user_path(uid):
    return _CONVO_DIR / f"{uid}.json"


def load_user(uid):
    p = _user_path(uid)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    return {"name": "", "msgs": 0, "note": "", "first_seen_cycle": None}


def _save_user(uid, rec):
    try:
        _user_path(uid).write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def note_for(uid):
    """One-line 'what I remember about this person', or ''."""
    return load_user(uid).get("note", "")


def _current_cycle():
    try:
        return json.loads(config.STATE_JSON.read_text(encoding="utf-8")).get("cycle")
    except Exception:
        return None


def touch_user(uid, name):
    rec = load_user(uid)
    rec["name"] = name or rec.get("name", "")
    rec["msgs"] = rec.get("msgs", 0) + 1
    if rec.get("first_seen_cycle") is None:
        rec["first_seen_cycle"] = _current_cycle()
    _save_user(uid, rec)
    return rec


def maybe_update_note(uid, ollama, channel_id, every=6):
    """Every `every` messages, distill a one-line memory of this person from the recent chat."""
    rec = load_user(uid)
    if rec.get("msgs", 0) == 0 or rec.get("msgs", 0) % every != 0:
        return
    convo = "\n".join(f'{m["name"]}: {m["content"]}' for m in _history[channel_id])[-1500:]
    if not convo.strip():
        return
    prompt = (f"From this recent chat, write ONE short line (max 20 words) capturing what you now "
              f"know or remember about {rec.get('name') or 'this person'} — their interests, or how "
              f"they relate to you. Write it as your own memory, no preamble.\n\n{convo}")
    try:
        note = ollama.chat(config.NARRATOR_MODEL, [{"role": "user", "content": prompt}],
                           options={"temperature": 0.5, "num_predict": 50}).strip()
        note = (note.splitlines()[0] if note.splitlines() else "").strip().strip('"')[:200]
        if note:
            rec["note"] = note
            _save_user(uid, rec)
    except Exception:
        pass
