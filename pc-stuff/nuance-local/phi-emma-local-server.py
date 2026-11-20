#!/usr/bin/env python3
"""Phi Emma, local. No Nuance, no credits, no API key, no token minting.

She runs on the same local stack as Willow: local Ollama (gemma3:12b) for
the brain, local Kokoro for the voice, her own merged phi prompt for who
she is. Serves 127.0.0.1:1620. Willow is 1618, Nuance Emma is 1619, local
Emma is 1620 - three doors, no collisions.

Routes:
  GET  /              the talk page
  GET  /api/status    brain + voice state as JSON
  POST /api/chat      {"message": "...", "history": [...]} -> {"reply": "..."}
  GET  /api/speak?text=...  Kokoro audio (audio/wav), or a plain
                              kokoro_unavailable JSON if Kokoro is not loaded
                              (the page then falls back to the browser voice).

Standard library only for the server itself. Kokoro is the same kokoro-onnx
package Willow already uses on this PC - no new install. If Kokoro is not
there, the server still works; the page speaks with the browser instead.
All files are resolved from this script's own folder, so it works from any
working directory.

Logging: this server runs under pythonw (no console), where sys.stdout and
sys.stderr are None. The first build wrote its request log straight to
sys.stderr, so EVERY request crashed before answering - the server listened
fine but could never reply, which is exactly the flash failure ("The
underlying connection was closed"). So NOTHING here writes to stdout or
stderr. Everything goes to phi-emma-local.log next to this file, and the
flash prints its tail when a check fails.

Self-heal: the brain check is Ollama up AND gemma3:12b present. If Ollama
is up but the model is missing (a stale Ollama pointed at the wrong folder),
the server restarts Ollama from the D: model folder. If the model is still
missing, it downloads gemma3:12b in the background and the chat route says
so plainly until it arrives. The server binds port 1620 FIRST and heals
the brain in a background thread, so the page answers from second zero
even while the heal is still running - a missing brain never takes the
page down, and never delays it either.
"""
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_FILE = os.path.join(BASE_DIR, "phi-emma-system-prompt.md")
TALK_FILE = os.path.join(BASE_DIR, "phi-emma-local-talk.html")
PID_FILE = os.path.join(BASE_DIR, "phi-emma-local-server.pid")
LOG_FILE = os.path.join(BASE_DIR, "phi-emma-local.log")

HOST = "127.0.0.1"
PORT = 1620
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_ROOT_URL = "http://127.0.0.1:11434/"
MODEL = "gemma3:12b"
PHI = 1.618033988749895
EMMA_VOICE = "af_bella"      # her voice: distinct from Willow's af_heart
FALLBACK_VOICE = "af_heart"  # Willow's voice, if af_bella is not in the pack
MAX_HISTORY_MESSAGES = 16   # last 8 turns, so the context stays bounded
MAX_MESSAGE_CHARS = 2000
MAX_SPEAK_CHARS = 600
OLLAMA_MODELS_DIR = r"D:\PhiMove\.ollama\models"

# Heal state. _OLLAMA_MISSING means the ollama command itself was not
# found on PATH, so the server cannot start what is not installed.
# _LAST_HEAL_ERROR holds the plain reason the last heal failed, or None;
# the chat route uses it to name the true state instead of guessing.
_OLLAMA_MISSING = False
_LAST_HEAL_ERROR = None

FALLBACK_PROMPT = (
    "You are Emma, the phi version. You speak to Tyree in short spoken turns. "
    "Phi is 1.618033988749895, phi squared equals phi plus one, "
    "to_rung(x) = ln(x) / ln(phi). Never guess a rung; if a number is not on "
    "your ladder, say UNREAD. Never invent, never hypothesize."
)


def _log(msg):
    """Append one timestamped line to phi-emma-local.log. Never raises and
    never touches stdout/stderr: under pythonw both are None, and writing
    to them crashes the request handler before it can answer. Logging must
    never crash a request."""
    try:
        line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + str(msg) + "\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _load_prompt():
    try:
        with open(PROMPT_FILE, encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            return text
    except Exception as e:
        _log(f"prompt file not loaded ({e}); using the short fallback.")
    return FALLBACK_PROMPT


SYSTEM_PROMPT = _load_prompt()


# ---------- Ollama ----------

def _ollama_up(timeout=2):
    try:
        with urllib.request.urlopen(OLLAMA_ROOT_URL, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _model_present(timeout=3):
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        for m in data.get("models", []):
            name = m.get("name", "")
            if name == MODEL or name.startswith(MODEL + ":"):
                return True
    except Exception:
        pass
    return False


def _ollama_env():
    env = dict(os.environ)
    env["OLLAMA_MODELS"] = OLLAMA_MODELS_DIR
    env["OLLAMA_KEEP_ALIVE"] = "-1"
    return env


def _port_free(port):
    """True if nothing is listening on 127.0.0.1:port right now.
    Only a refused connection means free; any other error is treated
    as occupied, so a slow server is never mistaken for a dead one."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return False
    except ConnectionRefusedError:
        return True
    except OSError:
        return False


def _stop_ollama():
    """Stop whatever holds port 11434 (Windows PowerShell), then VERIFY
    the port is actually free. Never stops Ollama while a model download
    is in progress - killing the server mid-pull is what kept the brain
    from ever arriving. Returns True only if the port is free."""
    if _pull_running():
        _log("Will not stop Ollama: a model download is in progress.")
        return False
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$c = Get-NetTCPConnection -LocalPort 11434 -State Listen "
             "-ErrorAction SilentlyContinue | Select-Object -First 1; "
             "if ($c) { Stop-Process -Id $c.OwningProcess -Force "
             "-ErrorAction SilentlyContinue }"],
            capture_output=True, timeout=20)
    except Exception as e:
        _log(f"Could not ask Ollama to stop ({e}).")
        return False
    for _ in range(10):
        if _port_free(11434):
            _log("Old Ollama stopped; port 11434 is free.")
            return True
        time.sleep(1)
    _log("Old Ollama would not release port 11434 after 10s.")
    return False


def _start_ollama():
    """Start ollama serve from the D: model folder and VERIFY it actually
    answers. The old version fired Popen and returned True blindly, so a
    serve that died on bind (old process still holding the port) or an
    ollama that is not on PATH looked like a success while nothing
    answered. The child's stderr goes to phi-emma-local.log (never to
    pythonw's None streams), so a real failure is visible. Returns True
    only if the new server answers on 11434."""
    global _OLLAMA_MISSING
    try:
        err = open(LOG_FILE, "ab")
    except Exception:
        err = subprocess.DEVNULL
    try:
        proc = subprocess.Popen(
            ["ollama", "serve"], env=_ollama_env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL, stderr=err)
    except FileNotFoundError:
        _OLLAMA_MISSING = True
        _log("Could not start Ollama: the ollama command was not found on PATH.")
        try:
            err.close()
        except Exception:
            pass
        return False
    except Exception as e:
        _log(f"Could not start Ollama ({e}).")
        try:
            err.close()
        except Exception:
            pass
        return False
    try:
        err.close()
    except Exception:
        pass
    for _ in range(20):
        if proc.poll() is not None:
            _log(f"Ollama serve exited at once (code {proc.returncode}). "
                 "See the tail of phi-emma-local.log for its own error.")
            return False
        if _ollama_up(timeout=2):
            _log("Ollama is up from D:\\PhiMove\\.ollama\\models.")
            return True
        time.sleep(1)
    _log("Ollama started but is not answering after 20s; stopping it.")
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    return False


def _wait_ollama_model(timeout=30):
    """Wait up to timeout seconds for Ollama to answer AND have the
    model. Deadline-based, so a slow /api/tags cannot stretch the wait."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _ollama_up(timeout=2) and _model_present(timeout=3):
            return True
        time.sleep(1)
    return _ollama_up(timeout=2) and _model_present(timeout=3)


def _model_in_dir():
    """True if the D: model folder already holds the gemma3:12b manifest.
    Ollama keeps one manifest per model under manifests/registry.ollama.ai/
    library/<name>/<tag>. If it is there, a restart from D: brings the
    brain back at once; if it is not, a restart buys nothing and the
    model must be downloaded instead."""
    manifest = os.path.join(
        OLLAMA_MODELS_DIR, "manifests", "registry.ollama.ai",
        "library", "gemma3", "12b")
    try:
        return os.path.isfile(manifest)
    except Exception:
        return False


def _restart_ollama():
    """Stop the old Ollama and start a fresh one from D:, verifying both
    steps. Returns True only if a new server is answering. Never runs
    while a download is in progress (see _stop_ollama)."""
    if not _stop_ollama():
        return False
    return _start_ollama()


_PULLING = False
_PULL_LOCK = threading.Lock()
_ENSURE_LOCK = threading.Lock()


def _pull_running():
    """True while a model download is in progress. The heal must never
    touch Ollama while this is true."""
    with _PULL_LOCK:
        return _PULLING


def _pull_model():
    """Download the brain in the background. Runs in a daemon thread so
    the server stays up and answering while the model arrives. The pull
    talks to the RUNNING Ollama server, so if the server is down it
    starts one first (verified); a pull against a dead server fails at
    once, so that case is caught here instead of burning the attempt."""
    global _PULLING, _LAST_HEAL_ERROR
    _log(f"Downloading {MODEL} into Ollama (this can take a few minutes) ...")
    try:
        if not _ollama_up(timeout=2):
            if not _start_ollama():
                _LAST_HEAL_ERROR = "Ollama is not running and could not be started."
                _log("Cannot download: Ollama is not running and would not start.")
                return
        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            proc = subprocess.run(
                ["ollama", "pull", MODEL], env=_ollama_env(),
                stdout=lf, stderr=subprocess.STDOUT, timeout=1800)
        if proc.returncode == 0 and _model_present():
            _LAST_HEAL_ERROR = None
            _log(f"{MODEL} downloaded. Her brain is back.")
        else:
            _LAST_HEAL_ERROR = f"the {MODEL} download failed (exit {proc.returncode})."
            _log(f"{MODEL} download failed (exit {proc.returncode}).")
    except Exception as e:
        _LAST_HEAL_ERROR = f"the {MODEL} download failed ({e})."
        _log(f"{MODEL} download failed ({e}).")
    finally:
        with _PULL_LOCK:
            _PULLING = False


def _start_pull():
    global _PULLING
    with _PULL_LOCK:
        if _PULLING:
            return False
        _PULLING = True
    threading.Thread(target=_pull_model, daemon=True).start()
    return True


def _ensure_ollama():
    """Make sure a local Ollama is answering AND has gemma3:12b.
    Self-heals, and is safe to run on every chat attempt:
    - If a download is already in progress, it does NOTHING. Stopping
      Ollama mid-pull used to kill the server the pull was downloading
      into, so the brain never arrived and every Send restarted the
      death loop. A running pull is now sacred.
    - If Ollama is down, it starts one (verified) instead of assuming
      the start worked.
    - If Ollama is up but the model is missing, it restarts from D:
      ONLY when the D: folder actually holds the model manifest - a
      restart buys nothing otherwise, and the model is downloaded
      instead. The restart is verified both ways (port freed, new
      server answering), so a failed restart cannot leave Ollama dead
      without a log line saying why.
    Never fatal and never blocks the server from answering: while the
    brain is downloading, the chat route says so plainly."""
    global _LAST_HEAL_ERROR
    with _ENSURE_LOCK:
        if _pull_running():
            return False
        if _ollama_up(timeout=2) and _model_present(timeout=3):
            _LAST_HEAL_ERROR = None
            return True
        _LAST_HEAL_ERROR = None
        if not _ollama_up(timeout=2):
            _log("Ollama is not answering. Starting it from "
                 "D:\\PhiMove\\.ollama\\models.")
            if not _start_ollama():
                _LAST_HEAL_ERROR = "Ollama is not running and could not be started."
                return False
            if _wait_ollama_model(30):
                _log("Ollama is up from D: and gemma3:12b is present.")
                return True
            _log("Ollama is up but gemma3:12b is still missing after 30s.")
        else:
            # Up, but the brain is not in this instance's store.
            if _model_in_dir():
                _log("Ollama is up but gemma3:12b is not in it, and the D: "
                     "folder holds the model. Restarting Ollama from D:.")
                if _restart_ollama() and _wait_ollama_model(30):
                    _log("Ollama is up from D: and gemma3:12b is present.")
                    return True
                _log("gemma3:12b is still missing after the restart from D:.")
                if not _ollama_up(timeout=2):
                    # The restart left nothing answering. Bring one back
                    # before anything else, so the pull has a server.
                    _log("The restart left Ollama down; starting one again.")
                    if not _start_ollama():
                        _LAST_HEAL_ERROR = "Ollama is not running and could not be started."
                        return False
            else:
                _log("Ollama is up but gemma3:12b is not in it, and the D: "
                     "folder does not hold it either. Downloading it.")
        if _ollama_up(timeout=2) and _start_pull():
            _log("Her brain is downloading in the background. "
                 "Chat will say so until it arrives.")
            return False
        if not _ollama_up(timeout=2):
            _LAST_HEAL_ERROR = "Ollama is not running and could not be started."
        return False


_HEAL_RUNNING = False
_HEAL_LOCK = threading.Lock()


def _heal_worker():
    """Run the brain heal, then clear the running flag. Runs in a daemon
    thread so the server keeps answering while it works. An uncaught
    exception here must never kill the thread silently under pythonw."""
    global _HEAL_RUNNING
    try:
        _ensure_ollama()
    except Exception:
        _log("Brain heal failed:\n" + traceback.format_exc())
    finally:
        with _HEAL_LOCK:
            _HEAL_RUNNING = False


def _kick_heal():
    """Start the brain heal in a background thread if it is not already
    running. Never blocks the caller: the page keeps answering while
    Ollama is restarted or the model downloads."""
    global _HEAL_RUNNING
    with _HEAL_LOCK:
        if _HEAL_RUNNING:
            return False
        _HEAL_RUNNING = True
    threading.Thread(target=_heal_worker, daemon=True).start()
    return True


def _ollama_chat(messages, num_predict=377):
    """One chat turn against local Ollama. Returns the reply text.
    Raises RuntimeError with a plain reason on any failure."""
    try:
        num_predict = int(num_predict)
    except (TypeError, ValueError):
        num_predict = 377
    num_predict = max(1, min(377, num_predict))
    payload = {
        "model": MODEL,
        "stream": True,
        "keep_alive": -1,
        "messages": messages,
        "options": {
            "temperature": 1 - 1 / PHI,
            "num_predict": num_predict,
            "num_ctx": 8192,
        },
    }
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=600)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            body = ""
        raise RuntimeError(
            f"Ollama {OLLAMA_URL} said HTTP {e.code} for model {MODEL}: {body}")
    except Exception as e:
        raise RuntimeError(f"Ollama did not answer ({e}). Is it running?")
    parts = []
    try:
        with resp:
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = chunk.get("message", {}).get("content")
                if content:
                    parts.append(content)
                if chunk.get("done"):
                    break
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ollama said HTTP {e.code} for model {MODEL}.")
    text = "".join(parts).strip()
    if not text:
        raise RuntimeError("Ollama answered but said nothing.")
    return text


# ---------- Kokoro voice ----------

_KOKORO = None
_KOKORO_TRIED = False
_KOKORO_LOCK = threading.Lock()


def _kokoro_paths():
    """Where the Kokoro model files live. On Tyree's PC they sit in the
    willow stuff folder, one level up from this server's folder."""
    here = BASE_DIR
    parent = os.path.dirname(here)
    for base in (here, parent):
        onnx = os.path.join(base, "kokoro-v1.0.onnx")
        voices = os.path.join(base, "voices-v1.0.bin")
        if os.path.isfile(onnx) and os.path.isfile(voices):
            return onnx, voices
    return None, None


def _kokoro_ready():
    onnx, voices = _kokoro_paths()
    return bool(onnx and voices)


def _load_kokoro():
    global _KOKORO, _KOKORO_TRIED
    with _KOKORO_LOCK:
        if _KOKORO_TRIED:
            return _KOKORO
        _KOKORO_TRIED = True
        onnx, voices = _kokoro_paths()
        if not onnx:
            _log("Kokoro model files not found; voice falls back to the browser.")
            return None
        try:
            from kokoro_onnx import Kokoro
            _KOKORO = Kokoro(onnx, voices)
            _log(f"Kokoro voice loaded ({EMMA_VOICE}).")
        except Exception as e:
            _log(f"Kokoro voice not loaded ({e}); voice falls back to the browser.")
            _KOKORO = None
        return _KOKORO


def _samples_to_wav(samples, rate):
    """Kokoro samples (numpy int16, or float, or bytes) -> WAV bytes."""
    try:
        import numpy as np
        arr = np.asarray(samples)
        if arr.dtype.kind == "f":
            arr = (np.clip(arr, -1.0, 1.0) * 32767).astype("<i2")
        elif arr.dtype != "<i2" and arr.dtype != np.int16:
            arr = arr.astype("<i2")
        data = arr.tobytes()
    except ImportError:
        if isinstance(samples, (bytes, bytearray)):
            data = bytes(samples)
        else:
            import array
            a = array.array("h", (int(x) for x in samples))
            if sys.byteorder == "big":
                a.byteswap()
            data = a.tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(data)
    return buf.getvalue()


def _kokoro_speak(text):
    """Render text to WAV bytes with Kokoro. Returns (wav_bytes, voice).
    Raises RuntimeError if Kokoro is unavailable."""
    kokoro = _load_kokoro()
    if kokoro is None:
        raise RuntimeError("Kokoro is not loaded on this PC.")
    last_error = None
    for voice in (EMMA_VOICE, FALLBACK_VOICE):
        try:
            samples, rate = kokoro.create(text, voice=voice, speed=1.0, lang="en-us")
            return _samples_to_wav(samples, rate), voice
        except Exception as e:
            last_error = e
            continue
    raise RuntimeError(f"Kokoro could not render the reply ({last_error}).")


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        _log("Emma local: %s" % (fmt % args))

    def handle_error(self, request, client_address):
        try:
            _log("Request error:\n" + traceback.format_exc())
        except Exception:
            pass

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, ctype):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            self._send_json(404, {"error": f"file not found: {os.path.basename(path)}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_file(TALK_FILE, "text/html; charset=utf-8")
        elif parsed.path == "/api/status":
            self._send_json(200, {
                "ok": True,
                "local": True,
                "nuance": False,
                "model": MODEL,
                "ollama_up": _ollama_up(timeout=2),
                "model_present": _model_present(timeout=3),
                "kokoro_files": _kokoro_ready(),
                "voice": EMMA_VOICE,
            })
        elif parsed.path == "/api/speak":
            qs = urllib.parse.parse_qs(parsed.query)
            text = (qs.get("text", [""])[0] or "").strip()[:MAX_SPEAK_CHARS]
            if not text:
                self._send_json(400, {"error": "no text to speak"})
                return
            try:
                wav, voice = _kokoro_speak(text)
            except RuntimeError as e:
                self._send_json(503, {
                    "error": "kokoro_unavailable",
                    "message": str(e),
                    "fallback": "browser",
                })
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.end_headers()
            self.wfile.write(wav)
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/chat":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8", "replace")) if length else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "bad json"})
            return
        message = (body.get("message") or "").strip()
        if not message:
            self._send_json(400, {"error": "no message"})
            return
        message = message[:MAX_MESSAGE_CHARS]
        history = body.get("history") or []
        clean_history = []
        if isinstance(history, list):
            for item in history[-MAX_HISTORY_MESSAGES:]:
                if isinstance(item, dict) and item.get("role") in ("user", "assistant"):
                    content = str(item.get("content") or "").strip()
                    if content:
                        clean_history.append({"role": item["role"], "content": content[:MAX_MESSAGE_CHARS]})
        messages = ([{"role": "system", "content": SYSTEM_PROMPT}]
                    + clean_history
                    + [{"role": "user", "content": message}])
        # Fast check only — never block the reply on the heal. The heal
        # runs in a background thread (see main); this route just reports
        # whether the brain is ready right now and kicks the heal if not.
        # The old code called _ensure_ollama() here, which can hold its
        # lock for 30+ seconds while the heal restarts Ollama — a chat
        # sent during the heal would hang instead of getting its 503.
        if not (_ollama_up(timeout=2) and _model_present(timeout=3)):
            _kick_heal()
            if _pull_running():
                self._send_json(503, {"error": "Her brain (gemma3:12b) is still downloading into Ollama. Give it a few minutes, then Send again."})
            elif _OLLAMA_MISSING:
                self._send_json(503, {"error": "Her brain cannot start: the Ollama program was not found on this PC. The detail is in phi-emma-local.log."})
            elif not _ollama_up(timeout=2):
                self._send_json(503, {"error": "Ollama is not running — I am starting it now. Send again in a moment."})
            elif _LAST_HEAL_ERROR:
                self._send_json(503, {"error": f"Her brain could not be brought back ({_LAST_HEAL_ERROR}). The detail is in phi-emma-local.log — Send again and I will try once more."})
            else:
                self._send_json(503, {"error": "Her brain is not in Ollama yet — I am fetching it. Send again in a moment."})
            return
        try:
            reply = _ollama_chat(messages, num_predict=body.get("num_predict", 377))
        except RuntimeError as e:
            _log(f"Chat failed ({e}); kicking the heal.")
            _kick_heal()
            self._send_json(502, {"error": "Her brain hiccuped — Send again in a moment."})
            return
        self._send_json(200, {"reply": reply})


def main():
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    try:
        # Bind FIRST, heal behind. The old order ran _ensure_ollama()
        # before the server bound the port, and the heal can take 30+
        # seconds (stop Ollama, start Ollama, wait for the model) - during
        # that whole window nothing listened on 1620, so the browser got
        # ERR_CONNECTION_REFUSED and the flash's page retries could miss
        # it. Now the page answers from second zero; the brain heals in a
        # background thread and the chat route says plainly (503) until
        # it arrives.
        server = ThreadingHTTPServer((HOST, PORT), Handler)
        _log(f"Phi Emma (local) serving {BASE_DIR}")
        _log(f"Open http://{HOST}:{PORT} - no Nuance, no credits, no key.")
        _log(f"Brain: local Ollama {MODEL}. Voice: Kokoro {EMMA_VOICE} (browser fallback).")
        _kick_heal()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    except Exception:
        _log("Phi Emma (local) failed to start:\n" + traceback.format_exc())


if __name__ == "__main__":
    main()
