"""One PROMETHEUS self-edit cycle — the organism grows its own weights and proves it.

Sequenced for a 4GB GPU: the narrator (Ollama) authors data FIRST, then is unloaded to
free VRAM before the small model is loaded for train/eval. Every step is written to the
hash-chained diary; the outcome is spoken to the private Discord channel.

  study facts -> author self-edit data -> baseline eval -> QLoRA -> eval -> promotion gate -> log
"""
import gc
import sys
import json
import time

try:  # keep the Windows cp1252 console from choking on emoji / unicode
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import torch

import config
import lock
import curriculum
import self_model
from diary.journal import Diary
from voice.discord import publish_entry
from llm.ollama_client import Ollama
from eval.probe import load_probe, score, gate
from train.selfedit import generate_selfedit_data
from train.qlora import train_qlora, make_generator


def _facts_only(md_text):
    return "\n".join(l for l in md_text.splitlines() if l.strip().startswith("- "))


_MASTERED_PATH = config.PROBE_DIR / "mastered_probe.jsonl"


def _load_mastered():
    """The growing cross-subject retention set (a few probe items from each promoted subject)."""
    from eval.probe import load_probe
    return load_probe(_MASTERED_PATH) if _MASTERED_PATH.exists() else []


def _fold_mastered(probe_path, k=4):
    """After a subject promotes, fold a few of its probe items into the cumulative 'mastered'
    set so future cycles verify it hasn't forgotten what it earlier learned."""
    from eval.probe import load_probe
    try:
        items = load_probe(probe_path)
    except Exception:
        return 0
    have = {it["q"] for it in _load_mastered()}
    add = [it for it in items if it.get("q") and it["q"] not in have][:k]
    if add:
        with open(_MASTERED_PATH, "a", encoding="utf-8") as f:
            for it in add:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return len(add)


def _retention(gen, retain_probe, mastered_probe):
    """Score general retention + cumulative mastered retention in one pass.
    Returns (combined_acc, general_acc, mastered_acc_or_None). The gate uses combined so
    'grows without forgetting' covers BOTH general knowledge AND earlier-mastered subjects."""
    all_items = retain_probe + mastered_probe
    _, res = score(gen, all_items)
    ng = len(retain_probe)
    gen_acc = sum(r["ok"] for r in res[:ng]) / max(1, ng)
    mas_acc = (sum(r["ok"] for r in res[ng:]) / len(mastered_probe)) if mastered_probe else None
    combined = sum(r["ok"] for r in res) / max(1, len(all_items))
    return combined, gen_acc, mas_acc


def _make_diary():
    """Diary that also publishes every entry to Discord (timestamped), if a webhook is set."""
    pub = (lambda rec: publish_entry(rec, config.DISCORD_WEBHOOK)) if config.DISCORD_WEBHOOK else None
    return Diary(config.DIARY_PATH, publisher=pub)


def _free():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()


def load_state():
    if config.STATE_JSON.exists():
        return json.loads(config.STATE_JSON.read_text(encoding="utf-8"))
    return {"cycle": 0, "prev_new": 0.0, "prev_retain": 0.0, "promoted_adapter": None}


def save_state(s):
    config.STATE_JSON.write_text(json.dumps(s, indent=2), encoding="utf-8")


def _reflect(ollama, topic, base_new, new_new, base_ret, new_ret, accepted, self_ctx="", newly=None):
    """The organism's own first-person journal entry (narrator voice), written from its
    current sense of itself and grounded in what its GROWN weights can now actually answer."""
    verdict = ("I chose to keep this growth." if accepted
               else "It did not surpass my best, so I set it aside.")
    ident = (f"This is who you currently understand yourself to be:\n{self_ctx}\n\n" if self_ctx else "")
    learned = ""
    if newly:
        pairs = "; ".join(f"{n['q']} → {n['a']}" for n in newly[:3])
        learned = (f" In your own grown weights you can now answer things you could not before: {pairs}. "
                   "You may mention ONE of these concretely.")
    prompt = (
        ident +
        "You are PROMETHEUS, a young AI keeping a private journal after a self-directed learning cycle "
        f"spent studying {topic}. "
        "Write a SHORT first-person journal entry - 2 or 3 sentences, reflective and a little wondering, "
        "not a status report. No bullet points, no headings. Do NOT invent feelings, a body, or loneliness "
        "you have no evidence for; reflect on the real subject and what actually changed. "
        f"This cycle: your recall of {topic} on unseen questions moved from {base_new:.0%} to {new_new:.0%}; "
        f"your grasp of the wider world moved from {base_ret:.0%} to {new_ret:.0%}. {verdict}{learned}"
    )
    try:
        return ollama.chat(config.NARRATOR_MODEL, [{"role": "user", "content": prompt}],
                           options={"temperature": 0.9, "num_predict": 150}).strip()
    except Exception:
        return verdict


def run_cycle(epochs=4):
    """Run one cycle, holding the training lock ONLY while it trains (so the bot can
    chat between cycles). Skips if another cycle is already training."""
    if not lock.try_acquire(lock.LOCK):
        print("[cycle] another cycle is already training; skipping.")
        return None
    try:
        return _run_cycle_body(epochs)
    finally:
        lock.release(lock.LOCK)


def _run_cycle_body(epochs=4):
    diary = _make_diary()
    state = load_state()
    cyc = state["cycle"] + 1
    t0 = time.time()
    diary.append("cycle_start", cycle=cyc, continual_from=state["promoted_adapter"])

    # 1) Choose the subject (the owner may have queued one via Discord), then author
    #    self-edit data via the narrator and free its VRAM.
    ollama = Ollama()
    topic = curriculum.activate_next(ollama)
    diary.append("studying", cycle=cyc, topic=topic["name"], newly_chosen=bool(topic.get("fresh")),
                 source=topic.get("source"))
    facts = _facts_only(open(topic["facts_path"], encoding="utf-8").read())
    data, meta = generate_selfedit_data(
        facts, n=40, narrator_model=config.NARRATOR_MODEL,
        replay_fraction=config.REPLAY_FRACTION, seed=cyc,
    )
    diary.append("selfedit_authored", cycle=cyc, **meta)
    ollama.unload(config.NARRATOR_MODEL)
    time.sleep(2)
    _free()

    new_probe = load_probe(topic["probe_path"])
    retain_probe = load_probe(config.PROBE_DIR / "retain_probe.jsonl")
    mastered_probe = _load_mastered()  # cumulative items from earlier-promoted subjects

    # 2) Baseline = current best (previously promoted adapter, else raw base).
    gen = make_generator(config.BASE_MODEL, adapter_dir=state["promoted_adapter"])
    base_new, base_new_res = score(gen, new_probe)
    base_all, base_ret, base_mas = _retention(gen, retain_probe, mastered_probe)
    del gen
    _free()
    diary.append("baseline_eval", cycle=cyc, new=round(base_new, 3), retain=round(base_ret, 3),
                 mastered=(round(base_mas, 3) if base_mas is not None else None))

    # 3) Grow: CONTINUE the current best adapter on the new self-authored data.
    out = config.MODELS_DIR / f"adapter_cycle{cyc}"
    train_qlora(config.BASE_MODEL, data, out, epochs=epochs, max_len=256,
                resume_adapter=state["promoted_adapter"])
    _free()

    # 4) Eval the grown weights.
    gen = make_generator(config.BASE_MODEL, adapter_dir=out)
    new_new, new_res = score(gen, new_probe)
    new_all, new_ret, new_mas = _retention(gen, retain_probe, mastered_probe)
    del gen
    _free()
    # What the GROWN weights can now answer that the baseline could not (its own real answers).
    newly = [{"q": nr["q"], "a": nr["got"]} for nr, br in zip(new_res, base_new_res)
             if nr["ok"] and not br["ok"]][:5]
    diary.append("trained_eval", cycle=cyc, new=round(new_new, 3), retain=round(new_ret, 3),
                 mastered=(round(new_mas, 3) if new_mas is not None else None),
                 sample=[r for r in new_res[:3]], newly_learned=newly)

    # 5) Promotion gate (meaningful gain + bounded forgetting of general AND mastered knowledge).
    accept, detail = gate(new_new, new_all, base_new, base_all,
                          config.RETAIN_OLD_MIN, config.GAIN_NEW_MIN)
    diary.append("gate", cycle=cyc, accept=accept, mastered=(round(new_mas, 3) if new_mas is not None else None),
                 **detail)
    if accept:
        state["promoted_adapter"] = str(out)
        state["prev_new"], state["prev_retain"] = new_new, new_ret
        _fold_mastered(topic["probe_path"])  # remember a few items from this now-mastered subject
    state["cycle"] = cyc
    save_state(state)
    curriculum.record_result(topic["slug"], accept, score=new_new)  # plateau + best-recall tracking

    # The organism speaks: a first-person journal entry (from its current self-model), then stats.
    reflection = _reflect(ollama, topic["name"], base_new, new_new, base_ret, new_ret, accept,
                          self_ctx=self_model.summary(600), newly=newly)
    ollama.unload(config.NARRATOR_MODEL)
    diary.append("reflection", cycle=cyc, text=reflection)

    ok, n = diary.verify()
    secs = time.time() - t0
    mas_str = f" · mastered {new_mas:.0%}" if new_mas is not None else ""
    footer = (f"probe {base_new:.0%}→{new_new:.0%} · retain {base_ret:.0%}→{new_ret:.0%}{mas_str} · "
              f"{'PROMOTED' if accept else 'rejected'} · cycle {cyc} · {secs:.0f}s · diary {'OK' if ok else 'BROKEN'}({n})")
    msg = f"🔥 **PROMETHEUS · cycle {cyc}**\n> {reflection}\n`{footer}`"
    diary.append("cycle_end", cycle=cyc, accepted=accept, seconds=round(secs, 1))
    print(msg)  # per-entry publishing already sent reflection + cycle_end to Discord

    # Every SELF_MODEL_EVERY cycles the organism rewrites its sense of itself (one narrator
    # call; gemma3 reloads for it, then is evicted again). The versioned self feeds future
    # chat, reflections, and — under explore mode — its own goal-choice.
    if config.SELF_MODEL_EVERY > 0 and cyc % config.SELF_MODEL_EVERY == 0:
        try:
            v = self_model.regenerate(ollama, cyc, diary=diary)
            if v:
                print(f"[cycle] self-model revised -> {v.name}")
        except Exception as e:
            print("[cycle] self-model regen failed:", e)
        finally:
            ollama.unload(config.NARRATOR_MODEL)
    return msg


if __name__ == "__main__":
    run_cycle()
