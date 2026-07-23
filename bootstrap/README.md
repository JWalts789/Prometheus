# PROMETHEUS Bootstrap — get OpenClaw + the organism up on the Mac

Carry this whole folder to the MacBook (AirDrop / USB / git). It pairs with two docs:
- **`Downloads/PROMETHEUS-Plan.html`** — the founding blueprint (mission, four bets, philosophy).
- **`Downloads/PROMETHEUS-Mac-OpenClaw-Transition.html`** — the Mac+OpenClaw architecture ("The Crossing").

> Honest pacing: getting OpenClaw **alive on a local model → your private Discord** is a ~1-hour job (Stage 1).
> Turning it into the safe, self-growing *organism* (the Keeper, the two planes, the weight loop) is a
> **multi-day build** (Stage 2 — the 14-day wedge in the plan). This README is the runbook; the files here
> are the starter scaffolds it references. Every command is a **starting point to verify on the machine** —
> macOS versions differ, and a few OpenClaw specifics (exact Discord keys, the install one-liner) should be
> confirmed against `docs.openclaw.ai`.

---

## The model caveat (read first — it changes the brain choice)

OpenClaw needs **reliable tool-calling** and likes **big context (~64k recommended)**. A 16GB M1 can't do 64k on a
7B comfortably, and 3–4B models are weak tool-callers. So:

- **Steady-state brain to START: `qwen2.5:7b`** (solid tool-calling) at **`num_ctx` ~16384**. If it's too slow/heavy,
  drop to `qwen2.5:3b` and expect rougher tool use.
- **Weight-growth (Tier 2) is now a fork:** on-device MLX LoRA is comfortable at **3–4B** but marginal at 7B on 16GB.
  Decide *after* Stage 1 whether to (a) keep a 7B brain and route nightly training to free **cloud T4**, or
  (b) run a 3–4B brain so training stays **fully local**. Don't pre-commit — get it alive first.

---

## Stage 1 — OpenClaw alive on a local model (~1 hour, do this first)

Run as your normal Mac user for now (we add the locked-down `prom`/`keeper` split in Stage 2). Keep it on **AC power**.

```bash
# 1. Foundations: Homebrew, Ollama + a tool-capable brain, MLX
bash scripts/00_foundations.sh        # installs brew, ollama, pulls qwen2.5:7b, sets up MLX venv

# 2. Install OpenClaw  (confirm the exact one-liner at https://docs.openclaw.ai/install)
curl -fsSL https://openclaw.ai/install.sh | bash      # OR:  npm install -g openclaw@latest

# 3. Onboard: pick Ollama -> "Local only" -> qwen2.5:7b, and connect your ONE private Discord channel
openclaw onboard

# 4. Point it at the local model explicitly (sanity)
ollama list
openclaw models list --provider ollama
openclaw models set ollama/qwen2.5:7b

# 5. Run the gateway (loopback only) and say hello from Discord
openclaw gateway run --bind loopback --verbose
```

**Local-Ollama config notes (from OpenClaw docs):** base URL is `http://127.0.0.1:11434` — **do NOT append `/v1`**
(that switches to OpenAI-compat mode where tool-calling is unreliable). The gateway default WebSocket port is `18789`.
If you prefer a config file, OpenClaw uses **JSON5** at `~/.openclaw/openclaw.json` with `models.providers.ollama.*`
and `agents.defaults.model.primary: "ollama/qwen2.5:7b"`.

**Stage-1 success = you message your private Discord channel, PROMETHEUS (running on your local 7B) replies, and it
can run a shell/file tool.** That's "it's alive." Stop here for the day if you want.

---

## Stage 2 — the leash + the organism (the multi-day build)

Now we make it *safe* and *self-growing*, following the two-plane design. Do these **in order**; don't skip the audit.

### 2a. OpenClaw capability audit (before anything else)
Walk the **9 questions** in the Transition HTML (§10). The load-bearing ones: confirm local Ollama works (✓ from Stage 1),
**disable the `elevated` escape hatch** (`tools.elevated.enabled=false`, empty `allowFrom`), and narrow the agent's
**workspace root** so filesystem tools can't see `~/.openclaw`. Use `openclaw sandbox explain` to inspect effective policy.

### 2b. The two planes (privilege separation)
```bash
sudo bash scripts/10_users_and_perms.sh   # creates keeper(admin)+prom, sets perms, makes the shared socket dir
```
Then, **as `prom`**, verify the fence: `ls /Users/keeper` MUST fail. Place `sandbox/prom.sb` under
`/Users/keeper/prometheus/profiles/` and from then on launch OpenClaw **wrapped**:
`sandbox-exec -f /Users/keeper/prometheus/profiles/prom.sb openclaw gateway run --bind loopback`.

### 2c. The Keeper's journal (the tamper-evident diary)
Run the hash-chained append-only journal **as `keeper`**:
```bash
sudo -u keeper python3 keeper/journal_daemon.py     # listens on /Users/Shared/prometheus/journal.sock
```
PROMETHEUS (as `prom`) appends by writing one JSON line to that socket and gets back `{seq, hash}` — it can *propose*
history but never *rewrite* it. Verify integrity anytime (and from the kill-switch):
```bash
sudo -u keeper python3 keeper/verify_chain.py       # exit 0 = intact, 1 = tampered
```

### 2d. The stable brain name (so the agent can't choose its own weights)
As `keeper`, build the indirection the agent points at:
```bash
sudo -u keeper ollama create prometheus-brain -f ollama/Modelfile.prometheus-brain
```
Set OpenClaw's model to `ollama/prometheus-brain`. On a promoted nightly LoRA, the **Keeper** edits the Modelfile's
`FROM`/`ADAPTER` and re-runs `ollama create` — the agent never controls which weights `prometheus-brain` resolves to.

### 2e. Keep-alive + kill switch
Install `launchd/ai.prometheus.gateway.plist` (Keeper-owned) to start the gateway as `prom` under
`caffeinate`+`sandbox-exec` at boot, with `KeepAlive`. The **kill switch** is a small Keeper watchdog (Day 3 in the
checklist) that holds the gateway PID and `SIGKILL`s it on: loop/iteration cap exceeded, `verify_chain.py` failure,
egress-allowlist violation, or your "stop" message read independently from Discord.

### 2f. Then build Tier 1 → 2 → 3 from the plan
Tier 1 = the safe supervised loop writing to the journal (no weight changes). Tier 2 = the nightly self-edit → MLX LoRA
→ frozen-probe eval → promote/swap loop. Tier 3 = self-authored goals + skill library + the fission experiment. Reuse
CLERIC (`C:/Users/gimme/Verity/`): `cleric/agents/base.py`, `cleric/memory/store.py`, `cleric/orchestrator.py`.

---

## What's in this folder

| Path | What it is | Status |
|---|---|---|
| `scripts/00_foundations.sh` | Homebrew + Ollama + `qwen2.5:7b` + MLX venv | verify-on-Mac |
| `scripts/10_users_and_perms.sh` | create `keeper`+`prom`, perms, shared socket dir | verify-on-Mac, needs sudo |
| `sandbox/prom.sb` | Seatbelt profile fencing `prom` off from `~keeper` | **template — test before trusting** |
| `ollama/Modelfile.prometheus-brain` | the stable `prometheus-brain` name the agent points at | ready |
| `keeper/journal_daemon.py` | hash-chained append-only journal over a Unix socket (runs as `keeper`) | ready, stdlib-only |
| `keeper/verify_chain.py` | independent chain verifier; exit 1 on tamper | ready, stdlib-only |
| `launchd/ai.prometheus.gateway.plist` | Keeper-owned boot launcher (prom + caffeinate + sandbox-exec) | verify path with `which openclaw` |

## Honest caveats
- **`prom.sb` is a starting template.** Seatbelt/SBPL is finicky; the reliable guarantee here is the filesystem fence
  (deny `~keeper`). Network containment leans on the **credential design** (prom holds no outbound tokens — only the
  Keeper's proxy does), not on Seatbelt alone. Iterate with small test commands.
- **It's one machine = a research-safety boundary, not hard adversarial containment.** A macOS privilege-escalation
  exploit collapses both planes. The kept Windows box is the future *physically-separate* Keeper if you want true containment.
- **The outbound proxy + kill-switch watchdog** are described but not shipped as files yet (they depend on your Discord
  setup) — they're Day 3 of the checklist. Ask and I'll scaffold them next.
