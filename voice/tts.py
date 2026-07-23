"""ElevenLabs TTS — PROMETHEUS's spoken voice.

The only cloud piece in an otherwise-local organism. Raw `requests` (no SDK). MP3 output,
sha1 on-disk cache (repeat lines cost 0 credits). No key -> returns None, never raises, so
chat/journal keep working offline.
"""
import hashlib

import requests

import config

_API = "https://api.elevenlabs.io/v1/text-to-speech"
_warned = False


def enabled() -> bool:
    return bool(config.ELEVENLABS_API_KEY)


def synth(text, voice_id=None):
    """Synthesize `text` to an mp3 file; return its Path, or None if disabled/failed."""
    global _warned
    text = (text or "").strip()
    if not text:
        return None
    if not config.ELEVENLABS_API_KEY:
        if not _warned:
            print("[tts] no ElevenLabs key -> voice disabled (chat unaffected).")
            _warned = True
        return None
    voice_id = voice_id or config.ELEVEN_VOICE_ID
    text = text[:400]  # cap credits + latency
    h = hashlib.sha1(f"{voice_id}|{config.ELEVEN_MODEL}|{text}".encode("utf-8")).hexdigest()
    out = config.TTS_CACHE_DIR / f"{h}.mp3"
    if out.exists() and out.stat().st_size > 0:
        return out
    try:
        r = requests.post(
            f"{_API}/{voice_id}?output_format=mp3_44100_128",
            headers={"xi-api-key": config.ELEVENLABS_API_KEY},
            json={"text": text, "model_id": config.ELEVEN_MODEL,
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.6}},
            timeout=30,
        )
        if r.status_code != 200 or not r.content:
            print(f"[tts] ElevenLabs error {r.status_code}: {str(r.text)[:200]}")
            return None
        out.write_bytes(r.content)
        return out
    except requests.RequestException as e:
        print(f"[tts] request failed: {e}")
        return None


if __name__ == "__main__":
    print("enabled:", enabled())
    print("result:", synth("Hello. I am Prometheus, and this is my voice."))
