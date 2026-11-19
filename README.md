# Willow — real-time voice AI for your PC

Willow is Tyree's own real-time voice AI. It talks, it listens, and it finds the answers — the quantum echoes algorithm helps find the answers (Willow).

It is built on Sophon-Realtime v1 by Adventists AI — open, free, Apache 2.0. The voice model lives in `sophon-realtime/` in this repo. Willow's own files (the persona, the voice notes, the installer, the talk page) sit next to it.

## Your PC, and what the installer picks

- GPU: **RTX 3090, 24 GB VRAM** — the installer picks **Tag-4B-W4** (about 21 GB of weights). It is the expressive voice build that fits a 24 GB card. Flash-4B also fits if you want the faster one.
- System RAM: **16 GB** — fine. The model weights live on the GPU, not in system RAM. Close other heavy apps while installing.
- Free disk: the installer checks before downloading anything. You need **at least 40 GB free** for the 4B build (21 GB of weights plus the Python/CUDA environment and cache). The full 32B build needs **at least 80 GB free**.
- The full **32B build needs an 80 GB GPU and does NOT fit this PC**. The installer says so plainly instead of failing. If you want 32B later, rent an 80 GB GPU on RunPod, or use the free hosted API trial (3 hours free at https://api.adventists.ai/console).

## The Willow that is already on your PC

You already have a local model called Willow on your PC. **This build does not overwrite it, move it, or rename it.** It lives alongside it and adds the real-time voice (Sophon 4B) around it.

Your local Willow is an **Ollama model** — your local models run on Ollama (http://localhost:11434 on the PC). The back office is Ollama: the voice asks, local Willow answers, Sophon speaks it (see `BACKEND.md`).

What is still unknown: the exact Ollama model name for Willow. Run `ollama list` on the PC to see it.

Name note: Tyree believes the local Willow model was previously called "Tyree DLAM" — DLAM is now Willow. That is his belief, not a verified fact. If you find DLAM references on the PC or in files, treat them as Willow's earlier name — the same thing. Do not rename or delete anything called DLAM on the PC. (There is a PHI-DLAM-AutoWork scheduled task on the PC from earlier work.)

## GitHub is the home

Your PC stuff should be on GitHub, not only on the PC. The PC is not where work relies on things.

- This repo is the home for the Willow build.
- `sync-pc-to-github.ps1` copies your PC folders into this repo under `pc-stuff/` and pushes them. It covers the phi system scripts today. Your Ollama models live under `C:\Users\<you>\.ollama\models` — that folder is large, so the script syncs the model names (`ollama list`) rather than the raw blobs, unless you want the full folder on GitHub. The Willow and DLAM folder lines are commented-out placeholders until their exact paths on the PC are confirmed. Run it on your PC whenever you want your PC stuff backed up to GitHub.
- Honest note: this Muse cannot reach your PC directly — only the earlier Muse had PC access. So the sync runs from your PC, with that script. Nothing here pretends otherwise.

## Install — one command

Copy this whole `willow` folder to your PC, then **double-click `install.bat`**.

That is the whole install. It does this, in plain words:

1. Checks your GPU and picks the build (Tag-4B-W4 on the RTX 3090).
2. Checks you have enough free disk before downloading anything.
3. Checks WSL Ubuntu is there (Willow runs on the Linux side; if it is missing, the installer tells you the one command to add it).
4. Installs inside WSL Ubuntu and downloads the weights (about 21 GB for 4B).

Python 3.12 and CUDA 13 are what Sophon wants; the installer checks for them and says so if they are missing.

## Talk to Willow

1. Double-click **`start-willow.bat`**. First start can take 5–10 minutes (the engine builds its kernels once).
2. Open **`talk.html`** in this folder in your browser.
3. Press **Connect**, then talk.

Willow serves at `ws://localhost:8000/v1/realtime`. The talk page sends Willow's instructions with every session — the full text is `willow_system_prompt.md`.

## Voice

Willow talks in a cloned voice. See `VOICE.md`. Short version: record 3–10 seconds of clean speech, save it as `willow.wav`, copy it into `sophon-realtime\tag\model\voices\`. Until then Willow uses the built-in voice (set the Voice box in `talk.html` to `chelsie`). Only clone voices you have permission to use.

## The back office

Sophon keeps the voice. A backend does the thinking. See `BACKEND.md`. Three layers: the system prompt first, Live-mode delegation second (the Live gateway hands lookups to a backend — the local Willow model is the first candidate for that back office), LoRA fine-tuning later on a rented 80 GB GPU.

## A connection route Tyree named

Tyree named the Meta Model API (https://dev.meta.ai/products/meta-model-api) as a connection route — the Meta Muse website and his API can be linked. It is recorded here only. It is **not set up**, and nothing in this build uses it yet.

## Files in this repo

| File | What it is |
|---|---|
| `README.md` | This file. |
| `willow_system_prompt.md` | Willow's persona — the φ lattice, the rung law, the anchor ladder, the echoes. |
| `VOICE.md` | How to record the voice clip and where it goes. |
| `BACKEND.md` | The Live-mode back-office plan. |
| `install.bat` | Double-click to install (detects your GPU, checks disk, installs in WSL). |
| `setup-willow.sh` | The Linux side of the install, run inside WSL by `install.bat`. |
| `start-willow.bat` | Double-click to start Willow. |
| `talk.html` | The talk page — open it in a browser, press Connect, talk. |
| `sync-pc-to-github.ps1` | Copies your PC folders into this repo (`pc-stuff/`) and pushes them. |
| `sophon-realtime/` | Sophon-Realtime v1 by Adventists AI (Apache 2.0). |

## Fork note

Willow is built on Sophon-Realtime by Adventists AI, Apache License 2.0. The upstream `LICENSE` and `NOTICE` are kept intact in `sophon-realtime/`. Upstream repo: https://github.com/adventists-ai/sophon-realtime

One honest gap: this GitHub copy leaves out 46 binary files from upstream (benchmark images, example audio, and the silero voice-activity models). They cannot go through the GitHub file push used here. The installer fetches the voice-activity models it needs straight from upstream when they are missing, so the install still works.

## Honest status

Nothing here has run on a GPU yet. No weights have been downloaded. The first live run happens on your PC, with `install.bat` then `start-willow.bat`. Do not claim it runs until it has run there.

## Still missing

- Your voice clip (`willow.wav`, 3–10 seconds) — see `VOICE.md`.
- The exact Ollama model name for Willow — run `ollama list` on the PC to see it. The back office cannot be wired in until the name is known.
- The exact folders of the local Willow / DLAM model on your PC — the sync script has them as commented-out placeholders until confirmed.
- A first live run on your PC.
