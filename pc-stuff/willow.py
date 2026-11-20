# willow.py - Willow, Tyree's local voice agent
# Hears you (Whisper), thinks (Ollama gemma3:12b), talks back (Windows voice),
# and runs PowerShell commands only after you say "yes".
#
# Talk:  "Willow, open notepad"   "Willow, what time is it"
#        "Willow sleep" / "Willow wake"   "Willow goodbye" (quit)

import json
import math
import queue
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import whisper
import pyttsx3

# ---------- phi settings ----------
PHI = (1 + math.sqrt(5)) / 2            # 1.618...
SAMPLE_RATE = 16000
BLOCK_SEC = 0.1
SILENCE_END_SEC = 1 / PHI               # 0.618 s of quiet ends a sentence
MAX_UTTERANCE_SEC = 13                  # Fibonacci cap on one sentence
PRE_ROLL_BLOCKS = 3                     # keep 0.3 s before speech starts
NOISE_MULT = PHI ** 2                   # speech = noise floor x 2.618
MIN_THRESHOLD = 0.01

# ---------- model settings ----------
# The brain is whichever Ollama lists gemma3:12b - 11434 normally,
# 11435 when the fallback is serving it (see willow_type / Emma's
# server: the stuck 11434 is never killed, a second Ollama on 11435
# serves the brain instead). Resolved fresh per think().
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_FALLBACK_URL = "http://localhost:11435/api/chat"
LLM_MODEL = "gemma3:12b"


def _brain_url():
    for base in ("http://127.0.0.1:11434", "http://127.0.0.1:11435"):
        try:
            with urllib.request.urlopen(base + "/api/tags", timeout=3) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            for m in data.get("models", []):
                name = m.get("name", "")
                if name == LLM_MODEL or name.startswith(LLM_MODEL + ":"):
                    return base + "/api/chat"
        except Exception:
            continue
    return OLLAMA_URL
WHISPER_MODEL = "base.en"
WAKE_WORDS = ("willow", "willa", "willo", "will o")
HISTORY_TURNS = 8
LOG_FILE = Path(__file__).with_name("willow_log.txt")

SYSTEM_PROMPT = (
    "You are Willow, Tyree's voice assistant on his Windows 11 PC. "
    "Reply ONLY with JSON: {\"say\": \"...\", \"command\": \"...\"}. "
    "\"say\" is what you speak, at most two short sentences. "
    "\"command\" is ONE PowerShell command that does what he asked, or \"\" if no command is needed. "
    "Open apps with Start-Process (notepad, calc, explorer, a URL). "
    "Never delete, move, or overwrite files, never format disks, never shut down or restart, "
    "never edit the registry, never download or run scripts from the internet, "
    "and never touch D:\\VEIL-OMNI or any Unreal project. If asked to, refuse in \"say\" with an empty command."
)

# Commands Willow will never run, even if the model writes them.
BLOCKED = re.compile(
    r"(remove-item|\brm\b|\bdel\b|\berase\b|\brd\b|rmdir|move-item|\bmv\b|rename-item|"
    r"\bformat\s+[a-z]:|format-volume|clear-disk|clear-content|set-content|out-file|stop-computer|restart-computer|"
    r"shutdown|reg\s+(add|delete)|remove-itemproperty|set-itemproperty|set-executionpolicy|"
    r"invoke-webrequest|\biwr\b|\bcurl\b|\bwget\b|invoke-expression|\biex\b|start-bitstransfer|"
    r"diskpart|bcdedit|cipher|takeown|icacls|veil-omni|\.uproject|\\content\\|\\source\\)",
    re.IGNORECASE,
)

YES_WORDS = ("yes", "yeah", "yep", "do it", "go ahead", "run it", "sure", "okay", "ok")


def log(line):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{stamp}  {line}\n")


class Willow:
    def __init__(self):
        print("Loading Whisper...")
        self.ear = whisper.load_model(WHISPER_MODEL)
        self.audio_q = queue.Queue()
        self.history = []
        self.awake = True
        self.threshold = MIN_THRESHOLD
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=int(SAMPLE_RATE * BLOCK_SEC),
            callback=self._on_audio,
        )

    def _on_audio(self, indata, frames, time_info, status):
        self.audio_q.put(indata.copy())

    def drain(self):
        while not self.audio_q.empty():
            try:
                self.audio_q.get_nowait()
            except queue.Empty:
                break

    def calibrate(self):
        print("Calibrating to room noise, stay quiet for 2 seconds...")
        self.drain()
        levels = []
        end = time.time() + 2
        while time.time() < end:
            block = self.audio_q.get()
            levels.append(float(np.sqrt(np.mean(block ** 2))))
        floor = float(np.median(levels)) if levels else 0.0
        self.threshold = max(floor * NOISE_MULT, MIN_THRESHOLD)
        print(f"Noise floor {floor:.4f}, speech threshold {self.threshold:.4f}")

    def record_utterance(self, timeout=None):
        pre_roll = []
        frames = []
        speaking = False
        silent_for = 0.0
        started = time.time()
        while True:
            block = self.audio_q.get()
            level = float(np.sqrt(np.mean(block ** 2)))
            if not speaking:
                pre_roll.append(block)
                pre_roll = pre_roll[-PRE_ROLL_BLOCKS:]
                if level > self.threshold:
                    speaking = True
                    frames = list(pre_roll)
                elif timeout and time.time() - started > timeout:
                    return None
                continue
            frames.append(block)
            silent_for = silent_for + BLOCK_SEC if level < self.threshold else 0.0
            if silent_for >= SILENCE_END_SEC or len(frames) * BLOCK_SEC >= MAX_UTTERANCE_SEC:
                break
        return np.concatenate(frames).flatten().astype(np.float32)

    def hear(self, timeout=None):
        audio = self.record_utterance(timeout)
        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            return ""
        result = self.ear.transcribe(audio, language="en", fp16=True)
        return result.get("text", "").strip()

    def say(self, text):
        if not text:
            return
        print(f"Willow: {text}")
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        self.drain()

    def think(self, user_text):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += self.history[-HISTORY_TURNS * 2:]
        messages.append({"role": "user", "content": user_text})
        payload = {
            "model": LLM_MODEL,
            "messages": messages,
            "stream": False,
            "format": "json",
            "keep_alive": -1, "options": {"temperature": 1 - 1 / PHI, "num_predict": 144},
        }
        req = urllib.request.Request(
            _brain_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                content = json.loads(resp.read())["message"]["content"]
        except Exception as e:
            return {"say": "My brain isn't back yet - I'm bringing it up myself, try again in a moment.", "command": ""}, f"error: {e}"
        try:
            reply = json.loads(content)
        except json.JSONDecodeError:
            reply = {"say": content[:200], "command": ""}
        reply.setdefault("say", "")
        reply.setdefault("command", "")
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": json.dumps(reply)})
        return reply, content

    def run_command(self, command):
        if BLOCKED.search(command):
            log(f"BLOCKED  {command}")
            self.say("I won't run that one. It could change or delete files.")
            return
        print(f"\nCommand: {command}")
        self.say("Want me to run it? Say yes or no.")
        answer = self.hear(timeout=8).lower()
        print(f"You: {answer}")
        if re.search(r"\b(no|nope|don't|stop|cancel)\b", answer) or not any(w in answer for w in YES_WORDS):
            log(f"DECLINED {command}")
            self.say("Okay, skipped.")
            return
        log(f"RUN      {command}")
        try:
            done = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = (done.stdout or "").strip()
            err = (done.stderr or "").strip()
            if out:
                print(out[:2000])
            if done.returncode == 0:
                log("RESULT   ok")
                self.say("Done.")
            else:
                print(err[:2000])
                log(f"RESULT   failed: {err[:300]}")
                self.say("That didn't work. The error is on screen.")
        except subprocess.TimeoutExpired:
            log("RESULT   timeout")
            self.say("That took too long, so I stopped it.")

    @staticmethod
    def strip_wake(text):
        clean = text.strip(" ,.!?")
        for w in WAKE_WORDS:
            m = re.match(rf"^(hey\s+)?{re.escape(w)}\b[\s,.!?]*", clean, re.IGNORECASE)
            if m:
                return True, clean[m.end():].strip(" ,.!?")
        return False, text

    def run(self):
        self.stream.start()
        self.calibrate()
        self.say("Willow is listening.")
        log("START")
        while True:
            heard = self.hear()
            if not heard:
                continue
            print(f"\nYou: {heard}")
            woke, rest = self.strip_wake(heard)
            low = rest.lower()

            if woke and low in ("", "hey", "hi"):
                self.awake = True
                self.say("Yes?")
                heard = self.hear(timeout=8)
                if not heard:
                    continue
                print(f"You: {heard}")
                rest, low = heard, heard.lower()
            elif not woke:
                continue

            if "goodbye" in low or "shut down willow" in low or "stop listening" in low:
                self.say("Goodbye, Tyree.")
                log("STOP")
                break
            if low.startswith("sleep"):
                self.awake = False
                self.say("Sleeping. Say Willow wake when you need me.")
                continue
            if low.startswith("wake"):
                self.awake = True
                self.say("I'm here.")
                continue
            if not self.awake:
                continue

            reply, raw = self.think(rest)
            log(f"HEARD    {rest}")
            log(f"MODEL    {raw}")
            self.say(reply["say"])
            command = str(reply.get("command", "")).strip()
            if command:
                self.run_command(command)
        self.stream.stop()


if __name__ == "__main__":
    try:
        Willow().run()
    except KeyboardInterrupt:
        print("\nWillow stopped.")
        sys.exit(0)


