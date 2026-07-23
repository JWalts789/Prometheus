"""Minimal Ollama client — PROMETHEUS's narration / WONDER voice.

requests-only, faithful to CLI-Anything's ollama_backend + generate.chat. Talks to
the local Ollama REST API. `unload()` evicts a model to free VRAM before training.
"""
import requests


class Ollama:
    def __init__(self, base_url="http://localhost:11434", timeout=180):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            requests.get(self.base + "/api/version", timeout=5)
            return True
        except requests.RequestException:
            return False

    def chat(self, model, messages, options=None, stream=False) -> str:
        payload = {"model": model, "messages": messages, "stream": stream}
        if options:
            payload["options"] = options
        r = requests.post(self.base + "/api/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def unload(self, model) -> None:
        """Free VRAM before a training run: keep_alive=0 evicts the model now."""
        try:
            requests.post(
                self.base + "/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=30,
            )
        except requests.RequestException:
            pass


if __name__ == "__main__":
    o = Ollama()
    print("available:", o.is_available())
    if o.is_available():
        reply = o.chat(
            "gemma3:4b",
            [{"role": "user", "content": "In one sentence, what is PROMETHEUS reaching for?"}],
            options={"temperature": 0.7, "num_predict": 60},
        )
        print("reply:", reply.strip())
