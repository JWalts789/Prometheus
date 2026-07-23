"""PROMETHEUS media orchestration — the GPU-sequenced image dance + the voice play-queue
+ the daily-images job. Kept in one place so the 4GB-card coordination is auditable.

GPU rule (single card): image generation acquires lock.LOCK (the general GPU lock),
evicts gemma3 from VRAM, boots ComfyUI, renders, stops ComfyUI (frees ~2.5GB), releases
the lock. While the lock is held, the bot's _training_active() defers chat, and a !learn
cycle's try_acquire(LOCK) skips — so nothing ever contends for VRAM.
"""
import json
import asyncio
from datetime import date

import discord

import config
import lock
import curriculum
from image import comfy
from image import prompt_craft
from voice import tts
from voice.discord import notify
from llm.ollama_client import Ollama

_ollama = Ollama()
_gpu_async_lock = asyncio.Lock()   # in-process: serialize image gen vs in-flight chat


class Busy(Exception):
    pass


# ---------------------------------------------------------------- image generation
async def image_session(items):
    """items = [(prompt, label), ...]. Boot ComfyUI once, render all, stop, return [Path]."""
    async with _gpu_async_lock:
        if not lock.try_acquire(lock.LOCK):
            raise Busy("I can't dream while I'm mid-cycle — try again once the journal settles.")
        loop = asyncio.get_event_loop()
        paths = []
        try:
            await loop.run_in_executor(None, _ollama.unload, config.NARRATOR_MODEL)  # free VRAM
            await loop.run_in_executor(None, comfy.ensure_server)
            for prompt, label in items:
                p = await loop.run_in_executor(None, lambda pr=prompt, lb=label: comfy.generate(pr, label=lb))
                paths.append(p)
        finally:
            if not config.COMFY_KEEP_WARM:
                await loop.run_in_executor(None, comfy.stop_server)
            lock.release(lock.LOCK)
        return paths


async def generate_one(prompt, label="imagine"):
    return (await image_session([(prompt, label)]))[0]


async def imagine(idea, label="imagine"):
    """Enhance the idea into a rich prompt (gemma3, guided by learned prompt-craft) BEFORE the
    session evicts gemma3, then render. Returns (png_path, enhanced_prompt)."""
    loop = asyncio.get_event_loop()
    enhanced = await loop.run_in_executor(None, prompt_craft.enhance, idea)
    path = (await image_session([(enhanced, label)]))[0]
    return path, enhanced


# ---------------------------------------------------------------- the grown weights SPEAK
def _grown_answer(question, max_new_tokens=64):
    """Blocking: load the promoted QLoRA adapter (the weights that actually GREW) and answer.
    torch/transformers are imported lazily so the bot stays light until someone asks."""
    import gc
    import json
    from train.qlora import make_generator
    try:
        st = json.loads(config.STATE_JSON.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    adapter = st.get("promoted_adapter")
    gen = make_generator(config.BASE_MODEL, adapter_dir=adapter, max_new_tokens=max_new_tokens)
    try:
        return gen(question).strip(), adapter
    finally:
        del gen
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


async def ask_grown(question):
    """GPU-sequenced: evict gemma3, load the grown adapter, answer, free. Returns (answer, adapter).
    Raises Busy if a cycle or image session is holding the GPU."""
    async with _gpu_async_lock:
        if not lock.try_acquire(lock.LOCK):
            raise Busy("I can't reach my grown mind while I'm mid-cycle — try again once the journal settles.")
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, _ollama.unload, config.NARRATOR_MODEL)  # free VRAM
            ans, adapter = await loop.run_in_executor(None, _grown_answer, question)
        finally:
            lock.release(lock.LOCK)
        return ans, adapter


# ---------------------------------------------------------------- voice play-queue
_voice_q = asyncio.Queue()


async def play_consumer():
    """Single consumer so ElevenLabs synth + playback stay ordered and never overlap."""
    while True:
        vc, text = await _voice_q.get()
        try:
            if not (vc and vc.is_connected()):
                continue
            loop = asyncio.get_event_loop()
            path = await loop.run_in_executor(None, tts.synth, text)
            if not path:                      # no key / error -> skip, stay connected
                continue
            while vc.is_playing():
                await asyncio.sleep(0.2)
            vc.play(discord.FFmpegPCMAudio(str(path), executable=config.FFMPEG_EXE))
            while vc.is_playing():
                await asyncio.sleep(0.2)
        except Exception as e:  # never let a bad line kill the voice loop
            print("[voice] play error:", e)


async def speak(vc, text):
    if vc and vc.is_connected() and tts.enabled():
        await _voice_q.put((vc, text))


# ---------------------------------------------------------------- daily images
def _latest_reflection():
    last = None
    try:
        for line in config.DIARY_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)["entry"]
            if e.get("kind") == "reflection":
                last = e.get("text")
    except Exception:
        pass
    return last


def _craft_prompt(instruction, fallback):
    try:
        out = _ollama.chat(config.NARRATOR_MODEL, [{"role": "user", "content": instruction}],
                           options={"temperature": 0.8, "num_predict": 90}).strip()
        out = out.splitlines()[0].strip().strip('"\'*` ')
        return out if len(out) > 12 else fallback
    except Exception:
        return fallback


async def daily_images(force=False):
    guard = config.LOGS_DIR / "daily_images.json"
    today = date.today().isoformat()
    if not force:
        try:
            if guard.exists() and json.loads(guard.read_text()).get("last") == today:
                return None
        except Exception:
            pass

    subject = curriculum.status().get("current") or "the pursuit of knowledge"
    refl = _latest_reflection() or "a young mind, wondering what it is"
    loop = asyncio.get_event_loop()
    subj_prompt = await loop.run_in_executor(
        None, prompt_craft.enhance, f"an evocative depiction of: {subject}")
    self_prompt = await loop.run_in_executor(
        None, prompt_craft.enhance,
        f"a surreal, dreamlike self-portrait of a nascent AI mind, evoking this private reflection: {refl[:180]}")

    paths = await image_session([(subj_prompt, subject), (self_prompt, "dream")])
    await loop.run_in_executor(None, notify,
                               f"📚 A vision of what I've been studying — *{subject}*.",
                               config.DISCORD_WEBHOOK, str(paths[0]))
    await loop.run_in_executor(None, notify, "💭 And a dream of myself.",
                               config.DISCORD_WEBHOOK, str(paths[1]))
    guard.write_text(json.dumps({"last": today}))
    return paths
