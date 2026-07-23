"""PROMETHEUS — central config. Everything tunable via env, sane local defaults."""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "models"
PROBE_DIR = ROOT / "probe"
LOGS_DIR = ROOT / "logs"
DIARY_PATH = LOGS_DIR / "diary.jsonl"
STATE_DB = ROOT / "state.db"        # APScheduler jobstore (later)
STATE_JSON = ROOT / "state.json"    # cycle counter + best-adapter pointer + last scores

# --- Ollama: the narration / WONDER voice (already pulled: gemma3:4b) ---
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
NARRATOR_MODEL = os.environ.get("PROM_NARRATOR", "gemma3:4b")

# --- The model that GROWS (HF id, trained via QLoRA, served in-process) ---
# Qwen2.5-1.5B-Instruct: more capacity to learn the domain AND retain general knowledge
# (0.5B proved the mechanism but forgot too much). Still fits the 4GB card in 4-bit.
BASE_MODEL = os.environ.get("PROM_BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")

# --- Discord voice ---
# Set via env var PROMETHEUS_DISCORD_WEBHOOK, OR drop the URL in secret_webhook.txt
# (gitignored). The file is read every process start, so the always-on task picks it up.
def _load_webhook():
    v = os.environ.get("PROMETHEUS_DISCORD_WEBHOOK", "").strip()
    if v:
        return v
    f = ROOT / "secret_webhook.txt"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return ""


DISCORD_WEBHOOK = _load_webhook()


# --- Discord BOT (two-way chat, SCOPED to its own channel; no admin, no actions) ---
# Token via env PROMETHEUS_BOT_TOKEN or secret_bot_token.txt (gitignored).
def _load_bot_token():
    v = os.environ.get("PROMETHEUS_BOT_TOKEN", "").strip()
    if v:
        return v
    f = ROOT / "secret_bot_token.txt"
    return f.read_text(encoding="utf-8").strip() if f.exists() else ""


BOT_TOKEN = _load_bot_token()
# The bot only reads/replies in its home channel: an explicit ID, or (if 0) any channel
# whose name contains BOT_CHANNEL_KEYWORD.
BOT_CHANNEL_ID = int(os.environ.get("PROM_BOT_CHANNEL_ID", "1525591582148001823") or "0")
BOT_CHANNEL_KEYWORD = os.environ.get("PROM_BOT_CHANNEL_KEYWORD", "prometheus")
# Only this Discord user may assign learning tasks (!learn). Others can only chat.
OWNER_ID = int(os.environ.get("PROM_OWNER_ID", "201844482000289792") or "0")

CURRICULUM_DIR = ROOT / "curriculum"

# --- The evolving self-model (versioned identity PROMETHEUS rewrites from its own diary) ---
# Every version is kept; the diffs are the evidence of an evolving self. It feeds chat,
# reflections, and (when explore/auto-learning is on) its goal-choice.
SELF_MODEL_DIR = ROOT / "self_model"
SELF_MODEL_EVERY = int(os.environ.get("PROM_SELFMODEL_EVERY", "5"))  # regenerate every N cycles

# --- Real-knowledge grounding (Wikipedia; no API key, one cached fetch per subject) ---
# Wikimedia asks for a descriptive User-Agent with contact info; a missing UA risks a 403.
WIKI_USER_AGENT = os.environ.get(
    "PROM_WIKI_UA", "PROMETHEUS-learner/0.1 (local study bot; gimmethatyout@gmail.com)")


# --- ElevenLabs TTS (cloud; the only non-local piece) ---
# Key via ELEVENLABS_API_KEY env or gitignored elevenlabs_key.txt. No key -> voice
# silently disabled (never crashes chat/journal).
def _load_eleven_key():
    v = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if v:
        return v
    f = ROOT / "elevenlabs_key.txt"
    return f.read_text(encoding="utf-8-sig").strip() if f.exists() else ""


ELEVENLABS_API_KEY = _load_eleven_key()
ELEVEN_VOICE_ID = os.environ.get("PROM_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel (swap freely)
ELEVEN_MODEL = os.environ.get("PROM_VOICE_MODEL", "eleven_turbo_v2_5")
TTS_CACHE_DIR = LOGS_DIR / "tts_cache"

# --- ffmpeg (Discord voice playback) ---
FFMPEG_EXE = (os.environ.get("PROM_FFMPEG") or shutil.which("ffmpeg")
              or r"C:\Users\gimme\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe")

# --- Image generation (local ComfyUI / SD1.5) ---
COMFY_DIR = Path(os.environ.get("PROM_COMFY_DIR", r"C:\Users\gimme\ComfyUI"))
COMFY_PYTHON = COMFY_DIR / "venv" / "Scripts" / "python.exe"
COMFY_MAIN = COMFY_DIR / "main.py"
COMFY_URL = os.environ.get("PROM_COMFY_URL", "http://127.0.0.1:8188")
# ComfyUI idle-holds ~2.5GB on this build, which would block gemma3 (3.3GB) from reloading
# for chat. So default to boot-per-session + stop-after to free VRAM. Set PROM_COMFY_WARM=1
# only if you have headroom.
COMFY_KEEP_WARM = os.environ.get("PROM_COMFY_WARM", "0") == "1"
IMAGES_DIR = LOGS_DIR / "images"
IMAGE_DAILY_HOUR = int(os.environ.get("PROM_IMAGE_HOUR", "9"))
IMAGINE_OWNER_ONLY = os.environ.get("PROM_IMAGINE_OWNER", "1") == "1"
# The subject PROMETHEUS studies to improve its own image-prompt craft; what it learns
# there feeds image/prompt_craft.enhance().
PROMPT_ENG_SUBJECT = os.environ.get(
    "PROM_PROMPTENG_SUBJECT", "professional prompt engineering for image generation")

# --- Promotion gate (anti-forgetting) ---
# Accept a new adapter iff it keeps >= RETAIN_OLD_MIN of the prior retained-score
# AND strictly improves on the day's failure class by > GAIN_NEW_MIN.
RETAIN_OLD_MIN = float(os.environ.get("PROM_RETAIN_MIN", "0.90"))
# Require a MEANINGFUL gain, not a single-question blip: >0.04 ≈ >~1 item on a ~20-item probe,
# so noise doesn't promote. (Was 0.0, which let sub-noise deltas thrash the adapter chain.)
GAIN_NEW_MIN = float(os.environ.get("PROM_GAIN_MIN", "0.04"))
REPLAY_FRACTION = float(os.environ.get("PROM_REPLAY", "0.4"))

for _d in (MODELS_DIR, PROBE_DIR, LOGS_DIR, TTS_CACHE_DIR, IMAGES_DIR, SELF_MODEL_DIR):
    _d.mkdir(parents=True, exist_ok=True)
