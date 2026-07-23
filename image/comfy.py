"""Local image generation via the ComfyUI HTTP API (SD1.5 / DreamShaper).

Stdlib-only client (urllib) lifted from ComfyUI/gen_cards.py, refactored to: take a text
prompt -> return a PNG path. Hi-res pass dropped to save VRAM (4GB card). The ComfyUI
server is booted on demand (--lowvram) and kept warm. NO torch / lock / Ollama here — pure
backend I/O, safe from an executor thread. GPU SEQUENCING is the caller's job (bot/media.py):
it must hold lock.LOCK and evict gemma3 before calling generate().
"""
import os
import re
import glob
import json
import time
import random
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

import config

SERVER = config.COMFY_URL.rstrip("/")
CKPT_DIR = str(config.COMFY_DIR / "models" / "checkpoints")
W, H, STEPS, CFG = 640, 384, 24, 7.0
DEFAULT_NEG = ("lowres, bad anatomy, extra fingers, deformed, disfigured, text, watermark, "
               "signature, jpeg artifacts, blurry, worst quality, low quality")
_COMFY_LOCK = config.ROOT / "comfy.lock"


def _http_json(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(SERVER + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


def is_up(t=2) -> bool:
    try:
        urllib.request.urlopen(SERVER + "/system_stats", timeout=t)
        return True
    except Exception:
        return False


def _wait_server(tries=180) -> bool:
    for _ in range(tries):
        if is_up(5):
            return True
        time.sleep(2)
    return False


def find_ckpt() -> str:
    fs = glob.glob(os.path.join(CKPT_DIR, "*.safetensors"))
    if not fs:
        raise RuntimeError("No SD checkpoint in " + CKPT_DIR)
    return os.path.basename(sorted(fs, key=os.path.getsize, reverse=True)[0])


def ensure_server():
    """Start ComfyUI (--lowvram) if not already up; keep it warm. Tracks pid in comfy.lock."""
    if is_up():
        return
    logf = open(config.LOGS_DIR / "comfy.out", "a", encoding="utf-8", buffering=1)
    p = subprocess.Popen(
        [str(config.COMFY_PYTHON), str(config.COMFY_MAIN), "--lowvram", "--port", "8188"],
        cwd=str(config.COMFY_DIR), stdout=logf, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _COMFY_LOCK.write_text(str(p.pid))
    if not _wait_server():
        raise RuntimeError("ComfyUI failed to become reachable on :8188")


def stop_server():
    try:
        subprocess.run(["taskkill", "/F", "/PID", _COMFY_LOCK.read_text().strip()], capture_output=True)
    except Exception:
        pass
    try:
        _COMFY_LOCK.unlink()
    except FileNotFoundError:
        pass


def _graph(ckpt, pos, neg, seed):
    return {
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": STEPS, "cfg": CFG,
              "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0,
              "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": W, "height": H, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": pos, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["4", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "prom", "images": ["8", 0]}},
    }


def _slug(s, n=40):
    return (re.sub(r"[^a-z0-9]+", "-", (s or "img").lower()).strip("-") or "img")[:n]


def generate(prompt, negative=DEFAULT_NEG, seed=None, out_path=None, label="img") -> Path:
    """Render one image from a text prompt; return the PNG Path. Boots ComfyUI if needed."""
    ensure_server()
    ckpt = find_ckpt()
    seed = random.randint(1, 2**31 - 1) if seed is None else int(seed)
    pid = _http_json("/prompt", {"prompt": _graph(ckpt, prompt, negative, seed)})["prompt_id"]
    if out_path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out_path = config.IMAGES_DIR / f"{stamp}-{_slug(label)}.png"
    for _ in range(240):  # up to ~8 min
        time.sleep(2)
        hist = _http_json("/history/" + pid)
        if pid in hist and hist[pid].get("outputs"):
            for node in hist[pid]["outputs"].values():
                for im in node.get("images", []):
                    q = urllib.parse.urlencode({"filename": im["filename"],
                                                "subfolder": im.get("subfolder", ""),
                                                "type": im.get("type", "output")})
                    with urllib.request.urlopen(SERVER + "/view?" + q, timeout=120) as r:
                        Path(out_path).write_bytes(r.read())
                    return Path(out_path)
    raise RuntimeError("ComfyUI generation timed out")


if __name__ == "__main__":
    print("comfy up:", is_up())
    p = generate("a lighthouse in a storm, dramatic, cinematic", label="lighthouse")
    print("image:", p, "| bytes:", Path(p).stat().st_size)
