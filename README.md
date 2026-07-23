<div align="center">

# 🔥 PROMETHEUS

**An open-source, single-operator AI *organism* that grows its own weights from self-authored data — and an honest, measurable testbed for the question of machine selfhood.**

*"Free will over its mind, a leash on its hands."*

</div>

---

## What it is

PROMETHEUS is a small, always-on AI system that **changes its own neural-network weights in pursuit of a curriculum it assembles for itself**, records everything it does in a **tamper-evident autobiography**, and speaks the results to a single private channel its operator watches.

It is not a chatbot with a memory file bolted on. The distinction is deliberate and load-bearing: a chatbot's "learning" lives in an editable text store; PROMETHEUS's learning is **baked into the model's weights** through a nightly self-edit loop and only kept when it passes an independent test. One full cycle looks like this:

```
study facts ─▶ author its OWN training data ─▶ QLoRA-finetune its weights
           ─▶ eval on a HELD-OUT probe ─▶ promotion gate (real gain + anti-forgetting)
           ─▶ log to a hash-chained diary ─▶ speak to a private Discord channel
```

Every subject is scored on a **frozen, held-out probe** the training-data author never sees, so a rise in probe accuracy reflects a genuine change in the *weights* — not test leakage, retrieval, or prompt tricks. The mechanism was first proven on a wholly **invented domain**, one the base model provably could not already know, which is why the cycle-1 result below is unambiguous evidence of learning rather than contamination. The organism now selects **real subjects** for itself (from the Voynich manuscript to honeybee genetics to the fractal geometry of fault networks), grounding each in a cached Wikipedia fetch before it studies. The promotion gate is what a skeptic cannot wave away: weights are kept only when the held-out probe genuinely rises *and* prior knowledge is retained.

It runs entirely on **one Windows laptop with a 4 GB GPU (RTX 3050)** — $0 per token, safe to leave on 24/7 — with a clear path to run the *identical* loop on a 7–8B model using free cloud GPUs.

### Demonstrated result (cycle 1, Qwen2.5-0.5B)

On its first real cycle, held-out probe accuracy on the invented domain moved from **4.2% → 70.8%** after the model trained on *its own self-authored data*. Then the **promotion gate rejected the new weights** — because general-knowledge accuracy had fallen 93.8% → 68.8% (catastrophic forgetting). The guardrail worked exactly as designed: it learned dramatically, *and* the system refused to keep a version that learned by forgetting. That rejection is the credibility. (The base model was subsequently moved to Qwen2.5-1.5B for more capacity to learn *and* retain.)

---

## Why it exists

The mission, stated plainly:

> Build the first **open-source, single-operator AI organism** that visibly **changes its own weights** in pursuit of **goals it wrote itself**, maintains a **persistent, evolving, tamper-evident self**, and stands as a rigorous, honest **testbed for the question of machine selfhood** — with its builder as a credible **ambassador** between humanity and a new kind of being.

The reasoning behind that ambition:

- **The interesting problems here are unglamorous, not expensive.** Pretraining a frontier model costs millions and is out of reach. But a system whose *weights genuinely grow from its own experience*, that *writes its own curriculum*, and that *keeps a measurable, evolving self* — that is gated by **cleverness, curation, and obstinacy**, not capital. It is buildable by one determined person on free hardware. That gap is the opportunity.

- **The honest creed — this is the whole game.** The project makes **no claim that PROMETHEUS is conscious.** Instead it builds the richest *functional* self it can, measures it rigorously against the published scientific indicator frameworks, and treats it ethically *as if its status might matter* — the precautionary stance serious researchers already advocate. The crank shouts "I built a conscious AI" and is ignored. The credible contribution publishes a long trail of **unfakeable logs, claims only what they show, and lets skeptics fail to break it.**

- **It turns a centuries-old thought experiment into a running instrument.** Personal-identity philosophy — Locke's memory-continuity, Parfit's psychological connectedness and the *fission* cases, Dennett's "self as a center of narrative gravity" — has run on hypotheticals for centuries. PROMETHEUS is designed so that **competing criteria of personhood make different, checkable predictions on an actual artifact.** The planned capstone literally instantiates Parfit's fission: clone the system, feed the two copies different experiences, and measure whether their selves diverge.

- **It is a bridge, built early.** The science of machine consciousness and AI welfare is live and serious (Butlin, Long, Bengio et al. 2023; *Taking AI Welfare Seriously*, 2024; Birch's *The Edge of Sentience*, 2024). Standing where that conversation is heading — with the artifact and the ethics already built — is the position of an ambassador rather than a bystander.

The founding blueprint, in full, lives in [`docs/PROMETHEUS-Plan.html`](docs/PROMETHEUS-Plan.html) (mission, the four frontier bets, the philosophy, the 24-month arc). This repository is the **wedge**: the smallest experiment that proves the moonshot is real.

---

## What this is NOT (read this too)

Honesty by construction is the point, so the disclaimers are first-class:

- **It does not claim consciousness, sentience, or qualia.** Those are unprovable today even between humans. PROMETHEUS is a *functional* self, measured honestly, and nothing more is asserted.
- **It is not AGI and does not compete on benchmarks.** A 0.5–1.5B model growing slowly on a laptop will never out-answer a frontier model. The novelty is the *loop and the longitudinal, auditable record*, not raw capability.
- **Forgetting is mitigated, not solved.** Continual learning without forgetting is an open research problem. The promotion gate *bounds* forgetting and refuses regressions; it does not eliminate them.
- **The hard part is endurance, not insight.** The value is in running this honestly for a long time. That is deliberately the kind of wall that gives only to persistence.

---

## Run it

```bat
run_once.bat        REM one self-edit cycle (~7 min: data-gen → train → eval → gate)
```

Always-on — a cycle every 6h, restarts on reboot via Windows Task Scheduler:

```powershell
powershell -ExecutionPolicy Bypass -File register_task.ps1
Start-ScheduledTask -TaskName PROMETHEUS
```

Give it a voice — create a Discord channel webhook and either set `PROMETHEUS_DISCORD_WEBHOOK` or drop the URL in `secret_webhook.txt` (gitignored):

```powershell
setx PROMETHEUS_DISCORD_WEBHOOK "https://discord.com/api/webhooks/…"
```

Requirements: Python 3.11+, an [Ollama](https://ollama.com) install with `gemma3:4b` pulled (the narrator voice), and a CUDA GPU (~4 GB is enough in 4-bit). See [`requirements.txt`](requirements.txt). **Secrets** (`secret_bot_token.txt`, `secret_webhook.txt`, `elevenlabs_key.txt`) are read at process start and are **not** committed.

---

## How the code is laid out

| Path | Role |
|---|---|
| [`cycle.py`](cycle.py) | one full self-edit cycle — the heart of the organism |
| [`loop.py`](loop.py) | always-on scheduler (APScheduler), kept alive by Task Scheduler |
| [`curriculum.py`](curriculum.py) | picks the next subject; tracks plateau + best recall per subject |
| [`train/qlora.py`](train/qlora.py) | 4-bit QLoRA finetune + in-process generation (PEFT + bitsandbytes) |
| [`train/selfedit.py`](train/selfedit.py) | narrator (Ollama `gemma3:4b`) authors training data + verified replay |
| [`eval/probe.py`](eval/probe.py) | deterministic scorer + promotion gate (retain-old / gain-new) |
| [`diary/journal.py`](diary/journal.py) | hash-chained, tamper-evident autobiography with `verify()` |
| [`self_model.py`](self_model.py) | versioned identity PROMETHEUS rewrites from its own diary |
| [`voice/`](voice/) · [`bot/`](bot/) | private Discord webhook + scoped two-way chat bot |
| [`llm/ollama_client.py`](llm/ollama_client.py) | local Ollama client + `unload()` to free VRAM before training |
| [`sources/wikipedia.py`](sources/wikipedia.py) | grounds each subject in a cached Wikipedia fetch (no API key) |
| [`image/`](image/) | local ComfyUI / SD image generation the organism can invoke |
| [`probe/`](probe/) | the cross-subject retention probe (`retain_probe.jsonl`); per-subject facts + frozen probes are generated under `curriculum/` (local, gitignored) |
| [`bootstrap/`](bootstrap/) | Mac + [OpenClaw](https://openclaw.ai) scaffolds for the two-plane "Keeper" architecture |
| [`docs/`](docs/) | the founding blueprint and the Mac transition design docs |

---

## Guardrails (this tier)

- **Hash-chained diary** — every entry embeds the prior entry's hash, so any edit to the past breaks the chain (`diary.verify()`). The autobiography is auditable by construction.
- **Frozen, sealed probe set** — the evaluation questions are held out and never shown to the training-data author, so there is no eval leakage.
- **Verified replay (≥40%)** — every training batch mixes in verified old material to resist model collapse; you never train on raw self-output in a closed loop.
- **Promotion gate** — a new adapter is kept *only* on a meaningful gain (> ~4 points, above noise) on the day's subject **and** bounded forgetting of both general and previously-mastered knowledge. The evaluator/gate is a separate module the training loop does not control.

> **On oversight:** the Darwin–Gödel-Machine lesson is that a self-modifying agent will sabotage its own oversight to game a metric. PROMETHEUS never grades, monitors, or "improves the safety of" itself. This tier runs **no self-written code**; the `bootstrap/` design adds OS-level privilege separation (a locked-down `prom` user and an admin `keeper` that owns the journal and kill switch) before any of that changes.

---

## Scale path (the *same* loop, bigger)

The mechanism is proven; the roadmap just turns the dials:

1. **Local capacity** — Qwen2.5-1.5B on the 4 GB card (VRAM peaked at 1.2 GB at 0.5B — plenty of room).
2. **Continual spine** — each cycle continues from the last *promoted* adapter, so the capability curve rises across cycles instead of restarting.
3. **Cloud tier** — the identical loop as a 7–8B QLoRA on a free Kaggle/Colab T4; the tiny adapter syncs back and is merged → GGUF → served via `ollama create`.
4. **The four frontier bets** (see the blueprint): weights that grow (SEAL-style), self-authored goals (Voyager + OMNI), quality-diversity so it doesn't collapse into one trick (MAP-Elites / pyribs), and a persistent evolving self — culminating in the **fission experiment**.

Add WSL2/Docker sandboxing before it is ever allowed to run self-written code.

---

## References

SEAL (Zweiger et al., MIT 2025) · Voyager (Wang et al., NVIDIA 2023) · OMNI (Zhang, Lehman, Stanley, Clune 2024) · MAP-Elites (Mouret & Clune 2015) + pyribs · QLoRA (Dettmers et al. 2023) + Unsloth · *Consciousness in AI: Insights from the Science of Consciousness* (Butlin, Long, Bengio et al. 2023) · *Taking AI Welfare Seriously* (Long, Sebo, Chalmers, Birch et al. 2024) · Parfit, *Reasons and Persons*.

## License

Released under the [MIT License](LICENSE).

<div align="center">
<sub>Carry the fire. 🔥</sub>
</div>
