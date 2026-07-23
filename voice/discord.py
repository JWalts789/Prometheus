"""Private Discord voice via webhook. If no webhook is set, prints locally instead
(so the loop never blocks on Discord). Set PROMETHEUS_DISCORD_WEBHOOK to go live.
"""
import os
import sys
import json
import time
from datetime import datetime

import requests

_ICON = {
    "loop_boot": "🌅", "cycle_start": "▶️", "studying": "📚", "selfedit_authored": "✍️",
    "baseline_eval": "📊", "trained_eval": "📈", "gate": "⚖️", "reflection": "📓",
    "cycle_end": "✅", "cycle_error": "⚠️", "loop_stop": "🌙", "self_model_revised": "🪞",
}


def _unix(ts):
    try:
        return int(datetime.fromisoformat(ts).timestamp())
    except Exception:
        return int(time.time())


def _fmt_entry(record):
    """Render one diary record as a timestamped Discord line. Uses Discord's <t:unix:T>
    tag so the time auto-localizes for every viewer."""
    e = record.get("entry", {})
    kind = e.get("kind", "note")
    icon = _ICON.get(kind, "·")
    stamp = f"`<t:{_unix(record.get('ts'))}:T>`"
    head = f"{stamp} {icon} **{kind}**"
    if kind == "reflection":
        return f"{head}\n> {e.get('text', '')}"
    if kind == "self_model_revised":
        return f"{head} — I rewrote my sense of myself (v{e.get('version')}, cycle {e.get('cycle')})"
    if kind in ("baseline_eval", "trained_eval"):
        mas = e.get("mastered")
        mas_s = f" · mastered {mas:.0%}" if isinstance(mas, (int, float)) else ""
        line = f"{head} — probe {e.get('new', 0):.0%} · retain {e.get('retain', 0):.0%}{mas_s}"
        nl = e.get("newly_learned") or []
        if kind == "trained_eval" and nl:
            line += "\n🌱 my grown weights can now answer: " + "; ".join(
                f"{n.get('q')} → {n.get('a')}" for n in nl[:3])
        return line
    if kind == "gate":
        v = "ACCEPT ✅" if e.get("accept") else "reject ✋"
        return (f"{head} — {v}  (probe {e.get('prev_new', 0):.0%}→{e.get('new', 0):.0%}, "
                f"retain {e.get('retain', 0):.0%})")
    if kind == "selfedit_authored":
        return (f"{head} — {e.get('self_generated', 0)} self-authored + "
                f"{e.get('replay_added', 0)} replay = {e.get('total', 0)} examples")
    if kind == "cycle_start":
        return f"{head} — cycle {e.get('cycle')} begins" + (
            f" (continuing from a promoted adapter)" if e.get("continual_from") else "")
    if kind == "studying":
        tag = " — *a subject you chose*" if e.get("newly_chosen") else ""
        src = f" · grounded in Wikipedia: *{e.get('source')}*" if e.get("source") else ""
        return f"{head} — now studying **{e.get('topic')}**{tag}{src}"
    if kind == "cycle_end":
        return (f"{head} — cycle {e.get('cycle')} "
                f"{'PROMOTED 🔥' if e.get('accepted') else 'no change'} · {e.get('seconds')}s")
    if kind == "loop_boot":
        return f"{head} — I am awake. diary {'intact' if e.get('diary_ok') else 'BROKEN'} ({e.get('entries')} entries)."
    if kind == "cycle_error":
        return f"{head} — {str(e.get('error', ''))[:400]}"
    extra = {k: v for k, v in e.items() if k != "kind"}
    return head + (f" · `{json.dumps(extra)[:300]}`" if extra else "")


def publish_entry(record, webhook_url):
    """Post a single diary entry to Discord, formatted + timestamped."""
    return notify(_fmt_entry(record), webhook_url)


def _safe_print(s):
    try:
        print(s)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(s.encode(enc, errors="replace").decode(enc, errors="replace"))


def notify(content, webhook_url=None, file_path=None) -> bool:
    url = (webhook_url or "").strip()
    if not url:
        _safe_print(f"[discord:unset] {content}")
        return False
    payload = {"content": content[:1900]}
    try:
        if file_path:  # multipart: JSON rides in payload_json alongside the file
            with open(file_path, "rb") as fp:
                r = requests.post(url, data={"payload_json": json.dumps(payload)},
                                  files={"files[0]": (os.path.basename(file_path), fp, "image/png")},
                                  timeout=60)
        else:
            r = requests.post(url, json=payload, timeout=15)
        return r.status_code in (200, 204)
    except requests.RequestException as e:
        _safe_print(f"[discord:error] {e}")
        return False


if __name__ == "__main__":
    # no webhook -> prints locally, returns False
    print("sent:", notify("PROMETHEUS is awake. (test — no webhook set)"))
