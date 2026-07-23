"""Turn a plain idea into a rich Stable Diffusion prompt.

gemma3 does the fluent wording, GUIDED by (a) a professional prompt-engineering baseline
(image/prompt_guide.md) and (b) whatever PROMETHEUS has personally STUDIED about prompt
engineering (the source_facts of its PROMPT_ENG_SUBJECT). So its learning shapes every
image, and improves as it studies the subject more. Falls back to a template on any error.
"""
import re

import config
import curriculum
from llm.ollama_client import Ollama

_GUIDE_PATH = config.ROOT / "image" / "prompt_guide.md"


def _guide():
    try:
        return _GUIDE_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


def _relevant(slug_name):
    n = slug_name.lower()
    return ("prompt" in n) or ("imagae" in n) or ("generation practice" in n) or ("image" in n and "generation" in n)


def _learned_facts():
    """What PROMETHEUS has personally studied about image generation / prompt craft (if anything).
    Searches its curriculum for any relevant subject it has actually studied."""
    facts = []
    try:
        for d in config.CURRICULUM_DIR.iterdir():
            if d.is_dir() and _relevant(d.name.replace("-", " ")):
                f = d / "source_facts.md"
                if f.exists():
                    facts.append(f.read_text(encoding="utf-8"))
    except Exception:
        pass
    return "\n\n".join(facts)[:4000]


def _fallback(idea):
    return f"{idea}, cinematic, dramatic lighting, highly detailed, concept art, intricate, masterpiece"


def enhance(idea, ollama=None) -> str:
    """Return a single-line SD prompt for `idea`. Never raises."""
    idea = (idea or "").strip()
    if not idea:
        return _fallback("a quiet moment")
    ollama = ollama or Ollama()
    learned = _learned_facts()
    learned_block = ("\n\nPRINCIPLES YOU HAVE PERSONALLY STUDIED (apply these):\n" + learned) if learned else ""
    system = (
        "You are an expert image-prompt engineer for a Stable Diffusion 1.5 model. Turn the user's "
        "idea into ONE single-line image prompt: comma-separated visual phrases only — front-load the "
        "concrete subject, then medium, style, lighting, composition, and quality tags. Translate any "
        "abstract idea into a depictable scene. No sentences, no explanation, output only the prompt.\n\n"
        + _guide() + learned_block
    )
    try:
        out = ollama.chat(
            config.NARRATOR_MODEL,
            [{"role": "system", "content": system},
             {"role": "user", "content": f"Idea: {idea}\nPrompt:"}],
            options={"temperature": 0.7, "num_predict": 130},
        ).strip()
        out = out.splitlines()[0].strip().strip('"\'*` ')
        out = re.sub(r"^(prompt|image)\s*:\s*", "", out, flags=re.I).strip()
        return out if len(out) >= 20 else _fallback(idea)
    except Exception:
        return _fallback(idea)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("learned facts present:", bool(_learned_facts()))
    for idea in ["the neurochemistry of addiction", "kintsugi", "a lighthouse in a storm"]:
        print(f"\n[{idea}]\n  -> {enhance(idea)}")
