# Willow's back office — Live-mode backend plan

Sophon keeps the voice. A backend does the thinking. That split is the whole design: the voice talks, the back office finds the answers.

## Layer 1 — the system prompt (first, always)

The voice gets its instructions every session. `willow_system_prompt.md` is the canonical text. `talk.html` sends it as the session instructions when you connect. The Live test page has the same box — paste it there too.

This layer alone makes Willow speak φ: the ladder, the round-trip rule, the superposition read, eudaimonia. No extra software needed.

Note: the voice engine's `/v1/chat/completions` endpoint uses the system prompt in `sophon-realtime/tag/config/system_prompt.json` (the model was tuned with it). Do not overwrite that file. Willow's prompt travels with the session, from the client, on top of it.

## Layer 2 — Live-mode delegation (second)

The Live gateway (`sophon-realtime/live/`) speaks the OpenAI GPT-Live protocol. It sits in front of the voice engine:

- Engine: `ws://127.0.0.1:8000/v1/realtime` (Tag build, port 8000)
- Gateway: `ws://127.0.0.1:8780/v1/live/sessions`
- Test page: `http://127.0.0.1:8780/` (upstream's page; its interface is in Chinese)

Sophon keeps talking and hands lookups to the backend through delegation. The backend answers, Sophon speaks the result. Start it after the engine is running:

```
cd sophon-realtime/live
BUILD=tag PORT=8000 LIVE_PORT=8780 bash start_live.sh
```

Note: Live mode downloads a small speech-recognition model (Qwen3-ASR-0.6B) on first start.

### The back office: Ollama, and the local Willow model

Tyree's local models run on Ollama — Willow is an Ollama model. Ollama serves on the PC at http://localhost:11434. See what is there with `ollama list` (models) and `ollama ps` (running models).

So the back office is Ollama: the Live gateway hands a lookup to Ollama, local Willow answers, Sophon speaks it. That is the first candidate, named — not a guess.

What is still unknown: the exact Ollama model name for Willow. Run `ollama list` on the PC to see it. Until the name is known, the backend stays a plan, not a wire-up. Do not overwrite, move, or rename anything belonging to the existing Willow.

### What the backend will answer (when wired)

- Rung lookups: `to_rung(x)` for any number, with the exact round-trip check.
- The anchor ladder: the rungs in `willow_system_prompt.md`, word for word.
- The ledger: entries and seals from the phi-ledger-cookie-chain repo, read-only.
- Tool calls the voice cannot do itself.

No API keys are invented here. The backend runs on the PC (localhost) or on a rented GPU. Nothing here phones home.

## Layer 3 — LoRA fine-tune (later)

Adapt the brain (persona, tone, domain knowledge) with LoRA in ms-swift on one 80 GB GPU — see `sophon-realtime/finetune/`. The voice, the sound tags, and the turn-taking are kept. This is the later option, not the first step: layers 1 and 2 come first, and only a rented 80 GB GPU can run the fine-tune.

## Name note

Tyree believes the local Willow model was previously called "Tyree DLAM" — DLAM is now Willow. That is his belief, not a verified fact. If you find DLAM references on the PC or in files, treat them as Willow's earlier name — the same thing. Do not rename or delete anything called DLAM on the PC.
