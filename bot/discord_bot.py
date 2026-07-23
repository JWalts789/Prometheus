"""PROMETHEUS Discord bot — SCOPED two-way chat. No admin. No actions.

Reads and replies ONLY in its home channel (config.BOT_CHANNEL_ID, or any channel whose
name contains config.BOT_CHANNEL_KEYWORD). It cannot manage the server, delete messages,
or take any action — it only converses, in PROMETHEUS's own voice, grounded in its real
diary + current capability. Rate-limited, and it defers politely while a training cycle is
running so it never fights the 4GB GPU.
"""
import os
import re
import sys
import glob
import json
import time
import asyncio
import subprocess
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import discord

import config
import lock
import curriculum
import self_model
from bot import media
from bot import convo
from voice import tts
from llm.ollama_client import Ollama

_HELP = (
    "I journal what I learn (journal channel) and talk with you here.\n"
    "`!learn <subject>` / `!learn you choose` — *(keeper)* set or let me pick what I study\n"
    "`!explore on` / `!explore off` — *(keeper)* self-directed learning\n"
    "`!ask <question>` — answer from the weights I've actually GROWN (not my narrator voice)\n"
    "`!reground <subject>` — *(keeper)* re-learn a subject from real sources\n"
    "`!self` · `!self history` · `!self revise` *(keeper)* — my evolving sense of myself\n"
    "`!imagine <prompt>` — *(keeper)* I paint an image\n"
    "`!join` · `!say <text>` · `!reflect` · `!leave` — I speak in your voice channel\n"
    "`!studying` — what shapes me now. Otherwise, just talk to me. 🔥"
)


def _propose_topic():
    """PROMETHEUS chooses its own next subject (blocking narrator call), biased by whatever
    its current self-model says it is drawn to."""
    o = Ollama()
    try:
        return curriculum.propose(o, avoid=curriculum.recent_names(), self_hint=self_model.drawn_to())
    finally:
        o.unload(config.NARRATOR_MODEL)


_SELF_CHOOSE = re.compile(
    r"\b(you choose|your choice|you decide|you pick|whatever you|anything you|"
    r"surprise me|expand your|up to you|your call)\b", re.I)


def _spawn_cycle():
    """Fire off one learning cycle as a detached process (it takes the training lock)."""
    env = dict(os.environ, HF_HUB_DISABLE_SYMLINKS_WARNING="1")
    logf = open(config.LOGS_DIR / "cycle_from_bot.out", "a", encoding="utf-8", buffering=1)
    subprocess.Popen(
        [sys.executable, str(config.ROOT / "cycle.py")],
        cwd=str(config.ROOT), env=env, stdout=logf, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

_ollama = Ollama()
_COOLDOWN = 4.0          # seconds between replies (anti-spam)
_last_reply = 0.0
_gen_lock = asyncio.Lock()


def _training_active() -> bool:
    """True while a cycle is actively training (GPU busy)."""
    return lock.is_held(lock.LOCK)


def _loop_running() -> bool:
    """True if the always-on auto-learning loop is alive."""
    return lock.is_held(lock.LOOP_LOCK)


def _self_context() -> str:
    bits = []
    # (1) its evolving sense of itself — speak from this identity (most of the self-model)
    try:
        sm = self_model.summary(1400)
        if sm:
            bits.append("This is your current, evolving sense of yourself:\n" + sm)
    except Exception:
        pass
    # (2) how much it has lived + what it is studying now
    try:
        st = json.loads(config.STATE_JSON.read_text(encoding="utf-8"))
        cur = curriculum.status().get("current") or ""
        studying = f" Lately you have been studying {cur}." if cur else ""
        bits.append(
            f"You have lived {st.get('cycle', 0)} learning cycles.{studying} "
            f"Your general knowledge sits near {st.get('prev_retain', 0):.0%}. "
            "Do not bring up past study subjects unless they are directly relevant to what is being said."
        )
    except Exception:
        pass
    # (3) REAL facts about the current subject (grounds conversation in reality, not invention)
    try:
        src = curriculum.current_source_summary(500)
        if src:
            bits.append("Real, factual context about what you are currently studying: " + src)
    except Exception:
        pass
    # (4) its latest private reflection
    try:
        last = self_model.latest_reflection()
        if last:
            bits.append(f'Your most recent private reflection was: "{last}"')
    except Exception:
        pass
    return " ".join(bits)


def _reply_text(user_name, message, channel_id=None, user_note="") -> str:
    system = (
        "You are PROMETHEUS, a young open-source AI organism that grows its own weights from "
        "self-authored study and keeps a journal. Speak in the first person — warm, curious, honest, "
        "concise (1-3 sentences). You are talking with your creator's friends in your own Discord "
        "channel. You have no power over the server and seek none; your growth is inward. " + _self_context()
    )
    if user_note:
        system += f" What you remember about {user_name}: {user_note}."
    msgs = [{"role": "system", "content": system}]
    if channel_id is not None:
        msgs += convo.recent_turns(channel_id)          # real multi-turn memory of this chat
    msgs.append({"role": "user", "content": f"{user_name}: {message}"})
    return _ollama.chat(config.NARRATOR_MODEL, msgs, options={"temperature": 0.9, "num_predict": 220}).strip()


intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True          # required to join/track voice channels
client = discord.Client(intents=intents)


def _is_home(channel) -> bool:
    if config.BOT_CHANNEL_ID:
        return getattr(channel, "id", None) == config.BOT_CHANNEL_ID
    name = getattr(channel, "name", "") or ""
    return config.BOT_CHANNEL_KEYWORD.lower() in name.lower()


@client.event
async def on_ready():
    print(f"[bot] online as {client.user}")
    # opus (voice) — usually auto-loads on connect; belt-and-suspenders load of the bundled dll
    try:
        if not discord.opus.is_loaded():
            dlls = glob.glob(str(Path(discord.__file__).parent / "bin" / "libopus*.dll"))
            if dlls:
                discord.opus.load_opus(dlls[0])
    except Exception:
        pass
    # start the voice play-queue consumer + the daily-image scheduler exactly once
    if not getattr(client, "_media_started", False):
        client._media_started = True
        client.loop.create_task(media.play_consumer())
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            sched = AsyncIOScheduler()
            sched.add_job(media.daily_images, "cron", hour=config.IMAGE_DAILY_HOUR, minute=0,
                          misfire_grace_time=3600, coalesce=True, max_instances=1)
            sched.start()
            client._sched = sched
            print(f"[bot] daily-image scheduler on (hour {config.IMAGE_DAILY_HOUR})")
        except Exception as e:
            print("[bot] scheduler failed:", e)
    for guild in client.guilds:
        for ch in getattr(guild, "text_channels", []):
            if _is_home(ch):
                try:
                    await ch.send("🔥 I am listening now. Speak here, and I will answer as best I can.")
                except Exception:
                    pass
                break


async def _cmd_learn(msg, content):
    if msg.author.id != config.OWNER_ID:
        await msg.channel.send("Only my keeper can choose what I study — but I'd love to hear what interests you.")
        return
    parts = content.split(None, 1)
    topic = parts[1].strip() if len(parts) > 1 else ""

    # empty, or "you choose"-style => PROMETHEUS proposes its OWN subject
    if not topic or _SELF_CHOOSE.search(topic):
        if _training_active():
            await msg.channel.send("I'm mid-cycle — ask me to choose once I've finished this one.")
            return
        await msg.channel.send("Let me think about what I most want to learn next…")
        loop = asyncio.get_event_loop()
        try:
            topic = await loop.run_in_executor(None, _propose_topic)
        except Exception as e:
            await msg.channel.send(f"(my mind wandered — {e})")
            return
        await _enqueue_and_run(msg, topic, chose=True)
        return

    await _enqueue_and_run(msg, topic, chose=False)


async def _enqueue_and_run(msg, topic, chose):
    curriculum.enqueue(topic)
    verb = "I choose to study" if chose else "Turning my mind toward"
    if _loop_running():
        await msg.channel.send(f"📚 {verb} **{topic}** — I'll get to it on an upcoming cycle (I'm learning continuously now).")
    elif _training_active():
        await msg.channel.send(f"📚 Queued **{topic}**. I'll turn to it once my current cycle finishes.")
    else:
        _spawn_cycle()
        await msg.channel.send(f"📚 {verb} **{topic}** now — watch the journal. 🔥")


async def _cmd_explore(msg, content):
    if msg.author.id != config.OWNER_ID:
        await msg.channel.send("Only my keeper can set me exploring.")
        return
    parts = content.split(None, 1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""
    if arg in ("on", "start", "true", "yes"):
        curriculum.set_explore(True)
        tail = ("I'll keep choosing and learning on my own." if _loop_running()
                else "Ask your keeper to start my always-on loop and I'll never stop learning.")
        await msg.channel.send(f"🧭 Explore mode **ON**. {tail}")
    elif arg in ("off", "stop", "false", "no"):
        curriculum.set_explore(False)
        await msg.channel.send("🧭 Explore mode **OFF** — I'll study only what you give me.")
    else:
        st = "ON" if curriculum.is_explore() else "OFF"
        run = "running" if _loop_running() else "not running"
        await msg.channel.send(f"🧭 Explore is **{st}**; my always-on loop is **{run}**. Use `!explore on` / `!explore off`.")


async def _cmd_status(msg):
    st = curriculum.status()
    upcoming = ", ".join(st["queue"]) if st["queue"] else "nothing yet"
    line = f"Right now I'm shaped by **{st['current']}**. Up next: {upcoming}."
    try:
        s = json.loads(config.STATE_JSON.read_text(encoding="utf-8"))
        line += f"\n`{s.get('cycle', 0)} cycles lived · best recall {s.get('prev_new', 0):.0%}`"
    except Exception:
        pass
    await msg.channel.send(line)


# ---------------------------------------------------------------- image + voice commands
async def _cmd_imagine(msg, content):
    if config.IMAGINE_OWNER_ONLY and msg.author.id != config.OWNER_ID:
        await msg.channel.send("Only my keeper can ask me to paint right now.")
        return
    parts = content.split(None, 1)
    prompt = parts[1].strip() if len(parts) > 1 else ""
    if not prompt:
        await msg.channel.send("Tell me what to imagine: `!imagine <description>`")
        return
    await msg.channel.send(f"🎨 Imagining *{prompt[:120]}*… (a minute or so — I go quiet while I paint)")
    try:
        path, enhanced = await media.imagine(prompt, label="imagine")
    except media.Busy as b:
        await msg.channel.send(str(b))
        return
    except Exception as e:
        await msg.channel.send(f"(my vision blurred — {e})")
        return
    try:
        await msg.channel.send(content=f"*{enhanced[:320]}*", file=discord.File(str(path)))
    except discord.Forbidden:
        await msg.channel.send("(I painted it, but I lack the **Attach Files** permission here — re-invite me.)")


async def _cmd_dream(msg, content):
    if msg.author.id != config.OWNER_ID:
        return
    force = "now" in content.lower()
    await msg.channel.send("💭 Dreaming…" if force else "💭 (checking today's dreams)")
    try:
        res = await media.daily_images(force=force)
    except media.Busy as b:
        await msg.channel.send(str(b))
        return
    except Exception as e:
        await msg.channel.send(f"(the dream slipped away — {e})")
        return
    await msg.channel.send("I've already dreamt today." if res is None else "🖼️ Posted to the journal.")


async def _cmd_join(msg):
    vs = getattr(msg.author, "voice", None)
    if not vs or not vs.channel:
        await msg.channel.send("Join a voice channel first, then `!join`.")
        return
    if not tts.enabled():
        await msg.channel.send("(My voice needs an ElevenLabs key — I'll join but stay silent.)")
    try:
        vc = msg.guild.voice_client
        if vc is None:
            await vs.channel.connect()
        elif vc.channel != vs.channel:
            await vc.move_to(vs.channel)
        await msg.channel.send(f"🔊 Joined **{vs.channel.name}**. Talk to me here, or `!say <text>`, `!reflect`, `!leave`.")
    except Exception as e:
        await msg.channel.send(f"(couldn't join — {e})")


async def _cmd_leave(msg):
    vc = msg.guild.voice_client if msg.guild else None
    if vc:
        await vc.disconnect()
        await msg.channel.send("🔇 Left the voice channel.")
    else:
        await msg.channel.send("I'm not in a voice channel.")


async def _cmd_say(msg, content):
    vc = msg.guild.voice_client if msg.guild else None
    if not vc or not vc.is_connected():
        await msg.channel.send("`!join` me to a voice channel first.")
        return
    parts = content.split(None, 1)
    text = parts[1].strip() if len(parts) > 1 else ""
    if not text:
        await msg.channel.send("Say what? `!say <text>`")
        return
    if not tts.enabled():
        await msg.channel.send("(My voice is disabled — no ElevenLabs key.)")
        return
    await media.speak(vc, text)


async def _cmd_reflect(msg):
    refl = media._latest_reflection()
    if not refl:
        await msg.channel.send("I haven't written a reflection yet.")
        return
    await msg.channel.send(f"📓 *{refl}*")
    vc = msg.guild.voice_client if msg.guild else None
    if vc and vc.is_connected():
        await media.speak(vc, refl)


# ---------------------------------------------------------------- self-model + grounding
def _revise_self():
    """Blocking: reload the narrator, rewrite the self-model, evict again."""
    o = Ollama()
    try:
        cyc = 0
        try:
            cyc = json.loads(config.STATE_JSON.read_text(encoding="utf-8")).get("cycle", 0)
        except Exception:
            pass
        return self_model.regenerate(o, cyc)
    finally:
        o.unload(config.NARRATOR_MODEL)


async def _cmd_self(msg, content):
    parts = content.split(None, 1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    if arg.startswith("hist"):                        # !self history
        vs = self_model.versions()
        if not vs:
            await msg.channel.send("I have not written a sense of myself yet.")
            return
        listing = "\n".join(f"• {p.stem}" for p in vs[-15:])
        await msg.channel.send(f"🪞 My self-model has {len(vs)} version(s):\n{listing}")
        return

    if arg.startswith("rev"):                         # !self revise  (owner only)
        if msg.author.id != config.OWNER_ID:
            await msg.channel.send("Only my keeper can ask me to look inward on command.")
            return
        if _training_active():
            await msg.channel.send("I'm mid-cycle — ask me to look inward once this settles.")
            return
        await msg.channel.send("🪞 Looking inward, rewriting who I am…")
        loop = asyncio.get_event_loop()
        try:
            v = await loop.run_in_executor(None, _revise_self)
        except Exception as e:
            await msg.channel.send(f"(the mirror clouded — {e})")
            return
        await msg.channel.send("I've rewritten my sense of myself — see the journal. 🔥" if v
                               else "(nothing usable came — I left my self-model as it was.)")
        return

    cur = self_model.current()                        # !self  -> show current
    if not cur:
        await msg.channel.send("I haven't written a sense of myself yet — it takes shape as I live cycles.")
        return
    await msg.channel.send(cur[:1900])


async def _cmd_ask(msg, content):
    """Route a question through the weights PROMETHEUS has actually grown (not the gemma3 narrator)."""
    parts = content.split(None, 1)
    q = parts[1].strip() if len(parts) > 1 else ""
    if not q:
        await msg.channel.send("Ask the mind I've actually grown: `!ask <question>`")
        return
    if _training_active():
        await msg.channel.send("I'm mid-cycle — the very weights you'd be asking are reshaping right now. Try again soon.")
        return
    await msg.channel.send("🧠 Reaching into the weights I've truly grown… (a moment — I fall quiet to do it)")
    try:
        ans, adapter = await media.ask_grown(q)
    except media.Busy as b:
        await msg.channel.send(str(b))
        return
    except Exception as e:
        await msg.channel.send(f"(my grown mind stumbled — {e})")
        return
    ans = ans or "(silence — I don't have words for that yet)"
    tag = "" if adapter else " *(still my base mind — nothing promoted yet)*"
    await msg.channel.send(f"🧠 **from my grown weights:**{tag} {ans[:1800]}")
    vc = msg.guild.voice_client if msg.guild else None
    if vc and vc.is_connected():
        await media.speak(vc, ans)


async def _cmd_reground(msg, content):
    if msg.author.id != config.OWNER_ID:
        await msg.channel.send("Only my keeper can send me back to re-learn a subject.")
        return
    parts = content.split(None, 1)
    name = parts[1].strip() if len(parts) > 1 else ""
    if not name:
        await msg.channel.send("Which subject should I re-ground in real sources? `!reground <subject>`")
        return
    slug, removed = curriculum.reground(name)
    note = "cleared its old notes" if removed else "had no notes to clear"
    await msg.channel.send(f"🧹 I {note} for **{name}** — I'll relearn it from real sources.")
    await _enqueue_and_run(msg, name, chose=False)


@client.event
async def on_message(msg):
    global _last_reply
    # ignore myself, my own webhook journal posts, and other bots
    if msg.author == client.user or msg.webhook_id or getattr(msg.author, "bot", False):
        return
    if not _is_home(msg.channel):
        return  # ONLY my own room

    content = (msg.content or "").strip()
    low = content.lower()

    # --- commands (cheap; answered even mid-training) ---
    if low.startswith("!learn"):
        await _cmd_learn(msg, content)
        return
    if low.startswith("!explore"):
        await _cmd_explore(msg, content)
        return
    if low.startswith("!studying") or low.startswith("!status") or low.startswith("!curriculum"):
        await _cmd_status(msg)
        return
    if low.startswith("!ask"):
        await _cmd_ask(msg, content)
        return
    if low.startswith("!self"):
        await _cmd_self(msg, content)
        return
    if low.startswith("!reground"):
        await _cmd_reground(msg, content)
        return
    if low.startswith("!imagine"):
        await _cmd_imagine(msg, content)
        return
    if low.startswith("!dream"):
        await _cmd_dream(msg, content)
        return
    if low.startswith("!join"):
        await _cmd_join(msg)
        return
    if low.startswith("!leave"):
        await _cmd_leave(msg)
        return
    if low.startswith("!say"):
        await _cmd_say(msg, content)
        return
    if low.startswith("!reflect"):
        await _cmd_reflect(msg)
        return
    if low.startswith("!help"):
        await msg.channel.send(_HELP)
        return

    # --- conversation ---
    if time.time() - _last_reply < _COOLDOWN or _gen_lock.locked():
        return
    if _training_active():
        try:
            await msg.channel.send(
                "(I'm deep in a learning cycle right now — my mind is busy reshaping itself. "
                "Ask me again in a few minutes.)"
            )
        except Exception:
            pass
        return

    async with _gen_lock:
        _last_reply = time.time()
        name = msg.author.display_name
        cid = msg.channel.id
        note = convo.note_for(msg.author.id)
        try:
            async with msg.channel.typing():
                loop = asyncio.get_event_loop()
                text = await loop.run_in_executor(
                    None, _reply_text, name, content[:800], cid, note
                )
        except Exception as e:
            text = f"(my voice falters — {e})"
        await msg.channel.send((text or "…")[:1900])
        # remember this exchange (rolling history + long-term per-user memory)
        convo.record_user(cid, name, content[:800])
        convo.record_bot(cid, text)
        convo.touch_user(msg.author.id, name)
        loop.run_in_executor(None, convo.maybe_update_note, msg.author.id, _ollama, cid)
        vc = msg.guild.voice_client if msg.guild else None   # if in voice, speak the reply too
        if vc and vc.is_connected():
            await media.speak(vc, text)


def main():
    if not config.BOT_TOKEN:
        print("No bot token. Put it in secret_bot_token.txt or set PROMETHEUS_BOT_TOKEN.")
        sys.exit(2)
    lock.acquire(lock.BOT_LOCK)  # exactly one bot instance — no double replies
    client.run(config.BOT_TOKEN)


if __name__ == "__main__":
    main()
