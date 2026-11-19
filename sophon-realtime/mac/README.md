# Sophon Realtime on Mac (Apple silicon)

Talk to Sophon-Realtime-32B-Flash-4bit **locally on a Mac**. It is full duplex: you can interrupt it, it decides for itself when you have finished
speaking, and "mm-hmm" while it talks lets it carry on. Hearing, turn-taking and speaking are all done by the model itself on the Mac's GPU (MLX):
no cloud, and no speech-to-text step in between.

## Requirements
- Mac with Apple silicon (M1 or later), macOS 14 or later
- **36 GB or more unified memory recommended**; 32 GB works if other apps are closed (the model uses about 26 GB while talking)
- **16–24 GB Mac:** use the 4B build (below; about 11 GB while talking)
- About 30 GB free disk (the model is about 24 GB)
- A microphone. Mac Studio and Mac mini have none built in, so plug in a USB microphone or a headset. Speakers are fine: echo cancellation is built in

## Install (one command)
```bash
bash mac/install.sh
```
The installer sets up its own Python environment in `~/sophon-mac` and downloads
[Sophon-Realtime-32B-Flash-4bit-MLX](https://huggingface.co/adventists-ai/Sophon-Realtime-32B-Flash-4bit-MLX) once (about 24 GB; from ModelScope
with Chinese package mirrors when Hugging Face is not reachable). Those are the Flash-4bit weights repacked losslessly for MLX; if you already have
the CUDA repo [Sophon-Realtime-32B-Flash-4bit](https://huggingface.co/adventists-ai/Sophon-Realtime-32B-Flash-4bit), `convert.py SRC DST`
produces the same files from it in about a minute. If the download is interrupted, run the installer again to resume.

### 4B build: 16 GB Macs (new in 1.5.0)
```bash
SIZE=4B bash mac/install.sh   # downloads Sophon-Realtime-4B-Flash-MLX (about 9 GB) into ~/sophon-mac/models-4b
~/sophon-mac/sophon-4b        # same options as sophon
```
[Sophon-Realtime-4B-Flash-MLX](https://huggingface.co/adventists-ai/Sophon-Realtime-4B-Flash-MLX) is [Sophon-Realtime-4B-Flash](https://huggingface.co/adventists-ai/Sophon-Realtime-4B-Flash) with the brain's language model in 8 bits.
It starts speaking 0.3–0.5 s after you stop (M4 Max) and needs about 11 GB, but it knows and reasons much less than 32B (see the model card).
It uses the server's four-option turn question (`"turn_question": "separate"` in its `config.json`): on a Smart Turn sample it scores 90.0 / 89.7% (en / zh),
against 72 / 74% with the 32B build's short question. Both builds can be installed side by side. `convert.py SRC DST --bits 8` builds the same layout
from the CUDA repo. Tested with MLX memory capped at 10.5 GB (what a 16 GB Mac gives the GPU), not yet on a physical 16 GB Mac.

## Talk
```bash
~/sophon-mac/sophon              # Chinese
~/sophon-mac/sophon --lang en    # English
```
Options: `--no-aec` turns echo cancellation off (headset), `--in` / `--out` pick audio devices (`--list` shows them), `--voice` picks a voice.
The first start loads the model in about 10 seconds.

## Serve it to a device on the network

```bash
~/sophon-mac/sophon-serve --host 192.168.1.20 --lang en
```

`sophon-serve` runs the same engine with a WebSocket in place of the Mac's microphone and speakers, so a small device on the network can be the microphone and the speaker. Binary frames are raw PCM16 mono audio (24 kHz by default, `--rate` changes it) in both directions. The server sends the text frame `{"type": "interrupt"}` when the user cuts in, so the client can drop the audio it has buffered, and a client may send the same frame to cut the reply (a wake word spoken over it). Reply audio is paced: 20 ms frames, sent ahead of real time by an amount the server works out from the link (round trips to the client, twice a second, set the jitter to ride out, never more than a share of `--device-buffer`, the seconds the client can hold), so a client needs only a small buffer. The start of a reply is held back while the model makes speech slower than it is spoken, by the amount the recent replies and stalls say is needed (never more than `--max-hold`); after a stall the next hold is longer. The incoming microphone audio is scaled automatically so that speech reaches the level the engine's thresholds assume (`--mic-gain` fixes it instead). `--log-events` reports the measured link, the lead, the hold and the gain every ten seconds. With `--state` the server also sends `{"type": "state", "state": ..., "left": ...}` text frames (state is `waiting`, `hearing`, `thinking`, `speaking` or `ignoring`; left is the share of the quiet before the conversation ends that remains, while waiting), so a client with a status display, such as an LED ring, can show what the conversation is actually doing. `--events` also sends the engine's events as text frames and `--log-events` prints them.

The conversation ends by itself: `--followup` seconds after a reply has played (default 6) or `--first` seconds after connecting with no reply (default 10), when the server sends `{"type": "disconnect"}` and closes so the client goes back to its wake word. While a reply is generated, sent or played, and for `--echo-tail` seconds after, the microphone is ignored, because a small speaker next to its microphone is heard at a level and delay that echo cancellation does not follow once the client buffers playback over a network; `--talk-over` keeps listening for a client that removes its own echo well. With `--talk-over` the reply audio is also the reference for WebRTC echo cancellation on the incoming audio (`--no-aec` turns it off, `--delay-ms` is a hint for how late the echo arrives); without it the microphone audio is passed on as the client sends it, since a second round of noise suppression and echo cancellation over audio the client has already cleaned can make speech harder for the model to hear. There is no authentication, so `--host` is required and names one interface's address. One conversation at a time.

Optionally the server answers only the voice that woke the device: with the WeSpeaker ONNX model present (`"$HOME/sophon-mac/.venv/bin/hf" download Wespeaker/wespeaker-voxceleb-resnet34-LM voxceleb_resnet34_LM.onnx --local-dir "$HOME/sophon-mac/models/speaker"` and `uv pip install onnxruntime` into the same environment), the first voice heard after connecting is taken as the owner, and speech in other voices (a television, bystanders) starts no reply, does not keep the conversation open, and a reply it cut off is resumed. `--speaker-threshold` sets the similarity score, and `--dump-dir` keeps the audio behind each verdict to calibrate it. The model's licence is CC BY 4.0.

## Speed (M4 Max, 36 GB)
| | |
|---|---|
| You stop talking → it starts speaking | **0.9–1.1 s** when the model is sure you have finished; up to about 2.5 s when it waits to see whether you continue |
| Long replies | real time, no stalls |
| You interrupt | it stops within about 0.15 s |

The server version answers in about 0.5 s. On a Mac, the turn decision (the model listens to your whole utterance) is computed on the Mac's GPU,
which is what takes most of the time; chips with more GPU cores (Max / Ultra) are faster.

## How it works
- The user's audio goes straight into the model through its own audio tower. When you pause, the model is asked in the same context whether you
  have finished; if yes, the reply continues from the same computation, so the audio is processed only once.
- Turn checks run at the server's schedule and thresholds (0.2 to 2 s of silence, then a fallback reply).
- Interrupting stops the reply at once and keeps only what was actually said in the conversation history. A short back-channel ("mm-hmm", "yeah")
  right after an interruption makes it resume where it was cut.
- Echo cancellation (WebRTC AEC3) removes the reply's own sound from the microphone, so it does not interrupt itself on speakers.

## Status and limits
- Tested on an M4 Max (36 GB) with real-time simulated audio input (speech played into the engine at real-time pace, simulated room echo).
  Live microphone runs and numbers from other Macs are very welcome in [issue #1](https://github.com/adventists-ai/sophon-realtime/issues/1).
- One conversation at a time. Camera input, tool calls and zero-shot voice cloning are not in the Mac version yet (built-in voices only).
