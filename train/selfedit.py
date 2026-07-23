"""Self-edit data generation — PROMETHEUS authors its own curriculum.

The narrator voice (Ollama, e.g. gemma3:4b) reads the source facts it chose to study
and writes diverse Q&A training examples. Mixed with ~20% VERIFIED REPLAY (general
knowledge) so finetuning doesn't collapse or catastrophically forget. The frozen probe
is NEVER shown here, so eval phrasings stay held-out.
"""
import re
import json
import random

from llm.ollama_client import Ollama

# General-knowledge replay — kept DISTINCT from the retain probe (no eval leakage).
REPLAY_POOL = [
    {"prompt": "What is 3 + 4?", "response": "7."},
    {"prompt": "Name a primary color.", "response": "Red."},
    {"prompt": "What is the capital of Italy?", "response": "Rome."},
    {"prompt": "What is the opposite of big?", "response": "Small."},
    {"prompt": "How many hours are in a day?", "response": "24."},
    {"prompt": "What sound does a dog make?", "response": "Woof."},
    {"prompt": "What is water made of?", "response": "Hydrogen and oxygen."},
    {"prompt": "What is the plural of 'mouse'?", "response": "Mice."},
    {"prompt": "What season comes after winter?", "response": "Spring."},
    {"prompt": "What is 5 times 2?", "response": "10."},
    {"prompt": "Which is larger, the sun or the moon?", "response": "The sun."},
    {"prompt": "What do bees make?", "response": "Honey."},
    {"prompt": "What is 8 + 5?", "response": "13."},
    {"prompt": "What is the capital of Spain?", "response": "Madrid."},
    {"prompt": "What color is grass?", "response": "Green."},
    {"prompt": "How many months are in a year?", "response": "12."},
    {"prompt": "What is the opposite of fast?", "response": "Slow."},
    {"prompt": "What do cows drink?", "response": "Water."},
    {"prompt": "What is frozen water called?", "response": "Ice."},
    {"prompt": "What is the largest ocean?", "response": "The Pacific."},
    {"prompt": "What is 20 divided by 4?", "response": "5."},
    {"prompt": "What planet do we live on?", "response": "Earth."},
    {"prompt": "What is the opposite of day?", "response": "Night."},
    {"prompt": "How many sides does a triangle have?", "response": "Three."},
]

_GEN_PROMPT = """You are building a study set for a student to memorize.
Using ONLY the facts below, write {n} diverse question-and-answer pairs that teach these facts.
Vary the phrasing and cover every fact. Keep each answer short (a few words).
Output ONLY a JSON array, like: [{{"q": "...", "a": "..."}}, {{"q": "...", "a": "..."}}]

FACTS:
{facts}
"""


def _parse_qa(text):
    out = []
    m = re.search(r"\[.*\]", text, re.S)
    if m:
        try:
            for o in json.loads(m.group(0)):
                if isinstance(o, dict) and o.get("q") and o.get("a"):
                    out.append({"prompt": str(o["q"]).strip(), "response": str(o["a"]).strip()})
        except Exception:
            pass
    if not out:
        for mo in re.finditer(r'\{[^{}]*"q"\s*:\s*"([^"]+)"[^{}]*"a"\s*:\s*"([^"]+)"[^{}]*\}', text, re.S):
            out.append({"prompt": mo.group(1).strip(), "response": mo.group(2).strip()})
    return out


def generate_selfedit_data(facts_text, n=40, narrator_model="gemma3:4b",
                           replay_fraction=0.2, seed=0, ollama=None):
    ollama = ollama or Ollama()
    raw = ollama.chat(
        narrator_model,
        [{"role": "user", "content": _GEN_PROMPT.format(n=n, facts=facts_text)}],
        options={"temperature": 0.8, "num_predict": 2048},
    )
    qa = _parse_qa(raw)
    if len(qa) < 12:  # underproduced -> one retry with more room
        raw2 = ollama.chat(
            narrator_model,
            [{"role": "user", "content": _GEN_PROMPT.format(n=n, facts=facts_text)}],
            options={"temperature": 0.8, "num_predict": 2600},
        )
        qa2 = _parse_qa(raw2)
        if len(qa2) > len(qa):
            qa = qa2
    n_self = len(qa)

    rng = random.Random(seed)
    base = max(len(qa), 1)
    k = max(1, round(base * replay_fraction / (1 - replay_fraction)))
    qa = qa + rng.sample(REPLAY_POOL, min(k, len(REPLAY_POOL)))
    rng.shuffle(qa)
    meta = {"self_generated": n_self, "replay_added": min(k, len(REPLAY_POOL)), "total": len(qa)}
    return qa, meta


if __name__ == "__main__":
    from pathlib import Path
    facts = (Path(__file__).resolve().parent.parent / "probe" / "source_facts.md").read_text(encoding="utf-8")
    data, meta = generate_selfedit_data(facts, n=40)
    print("meta:", meta)
    for ex in data[:6]:
        print("  ", ex)
