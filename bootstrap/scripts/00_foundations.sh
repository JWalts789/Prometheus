#!/usr/bin/env bash
# PROMETHEUS — Mac foundations.  RUN ON AC POWER.  For Stage 1, run as your normal
# user; later you'll re-run the model/MLX parts as the `prom` user.
# This is a STARTING POINT — verify each step; macOS versions differ.
set -euo pipefail

echo "==> [1/4] Homebrew"
if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Apple Silicon brew lives in /opt/homebrew — make sure it's on PATH:
  eval "$(/opt/homebrew/bin/brew shellenv)" || true
fi
brew --version

echo "==> [2/4] Ollama + a tool-capable local brain"
brew install ollama || true
# start the daemon (idempotent)
brew services start ollama 2>/dev/null || (ollama serve >/tmp/ollama.log 2>&1 &)
sleep 2
# Qwen2.5-7B has solid tool-calling, which OpenClaw needs. If 7B is too heavy on
# 16GB, swap the next line to:  ollama pull qwen2.5:3b  (expect rougher tool use).
ollama pull qwen2.5:7b
ollama list

echo "==> [3/4] MLX (on-device LoRA trainer) in a venv"
mkdir -p "$HOME/prometheus"
python3 -m venv "$HOME/prometheus/venv"
# shellcheck disable=SC1091
source "$HOME/prometheus/venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install --upgrade mlx mlx-lm
python -c "import mlx_lm, mlx.core as mx; print('mlx ok:', mx.default_device())"
deactivate || true

echo "==> [4/4] done."
echo "    Next: install OpenClaw (curl -fsSL https://openclaw.ai/install.sh | bash  OR  npm i -g openclaw@latest)"
echo "    then: openclaw onboard   (pick Ollama -> Local only -> qwen2.5:7b, connect your private Discord channel)"
