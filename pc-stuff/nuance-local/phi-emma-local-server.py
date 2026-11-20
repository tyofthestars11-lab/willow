#!/usr/bin/env python3
"""Phi Emma, local. No Nuance, no credits, no API key, no token minting.

She runs on the same local stack as Willow: local Ollama (gemma3:12b) for
the brain, local Kokoro for the voice, her own merged phi prompt for who
she is. Serves 127.0.0.1:1620. Willow is 1618, Nuance Emma is 1619, local
Emma is 1620 - three doors, no collisions. Willow and Emma share ONE
brain: the same gemma3:12b. It is normally served by the Ollama on
11434. That Ollama can get stuck: it stays up, does not list the
model, and cannot be killed from here (its port never frees and its
owner cannot be determined). So this server never fights it. When
11434 does not list gemma3:12b, this server brings up a SECOND Ollama
on 11435, pointed at the folder that holds the verified model, and
uses 11435 for chat. The stuck 11434 is left alone - it is idle, it
holds no model and no VRAM, and the 11435 server is the only one
loading gemma3:12b. If 11434 lists the model again, 11434 is used
and no second Ollama is started.

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

The brain: the model is already on this PC. The serving Ollama just
cannot see it, because it was started pointing at a folder that does
not hold it - so `ollama list` looks empty and the model looks missing.
This server FINDS the model on disk instead of downloading it again:
it scans D:\\PhiMove\\.ollama\\models then C:\\Users\\Admin\\.ollama\\models
for the gemma3:12b manifest and verifies EVERY blob it names - the blob
must exist, its size must match the manifest, and its SHA-256 must match
its digest. A half-moved or truncated copy passes an existence check
but Ollama rejects it, so a folder only counts when every blob verifies.
If a folder has it, a second Ollama is started on 11435 from that
folder and the start is PROVED: the 11435 server must list the model
before the fallback counts as done. The stuck Ollama on 11434 is
never killed and never restarted - killing it was tried and it does
not die, so it is left alone. If no folder has a complete verified
copy, the server says so plainly - naming the folders checked and
which blobs are bad - and stops. It never downloads. There is no
download anywhere in this file.

No console shell anywhere in this file either. Ollama is started
with hidden Python subprocesses (CREATE_NO_WINDOW), so no console
window ever flashes when the page loads or when Tyree presses Send.
The server binds port 1620 FIRST and heals the brain in a background
thread, so the page answers from second zero even while the heal is
still running - a missing brain never takes the page down, and never
delays it either.
"""
import hashlib
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
# The brain's ports. 11434 is the normal Ollama; 11435 is the fallback
# this server starts itself when 11434 is up but does not list the
# model (stuck, wrong folder, cannot be killed). 11434 is never killed.
OLLAMA_PRIMARY_PORT = 11434
OLLAMA_FALLBACK_PORT = 11435
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_ROOT_URL = "http://127.0.0.1:11434/"
MODEL = "gemma3:12b"


def _ollama_root_url(port):
    return "http://127.0.0.1:%d/" % port


def _ollama_tags_url(port):
    return "http://127.0.0.1:%d/api/tags" % port


def _ollama_chat_url(port):
    return "http://127.0.0.1:%d/api/chat" % port
PHI = 1.618033988749895
EMMA_VOICE = "af_bella"      # her voice: distinct from Willow's af_heart
FALLBACK_VOICE = "af_heart"  # Willow's voice, if af_bella is not in the pack
MAX_HISTORY_MESSAGES = 16   # last 8 turns, so the context stays bounded
MAX_MESSAGE_CHARS = 2000
MAX_SPEAK_CHARS = 600
OLLAMA_MODELS_DIR = r"D:\PhiMove\.ollama\models"
OLLAMA_MODELS_C_DIR = r"C:\Users\Admin\.ollama\models"
# The model folders on this PC, in the order they are checked. D: is the
# configured OLLAMA_MODELS and is checked first; C: is the stale copy
# from before the move.
MODEL_DIRS = [OLLAMA_MODELS_DIR, OLLAMA_MODELS_C_DIR]

# Heal state. _OLLAMA_MISSING means the ollama command itself was not
# found on PATH, so the server cannot start what is not installed.
# _LAST_HEAL_ERROR holds the plain reason the last heal failed, or None;
# the chat route uses it to name the true state instead of guessing.
# _LAST_HEAL_AT / _LAST_HEAL_RESULT give the heal a short memory so a
# Send cannot make it redo expensive work (start a fallback Ollama, rescan)
# over and over: if the last heal already concluded the model is not
# on disk, the next Sends just report that state until the cooldown
# passes. _LAST_FALLBACK_DIR / _LAST_FALLBACK_AT remember the last
# 11435 start, so the server never starts a second Ollama from the same
# folder twice in a row when it did not help. _OLLAMA_PROC is the 11435
# Ollama process this server started itself. _ACTIVE_OLLAMA_PORT is the
# port whose Ollama lists gemma3:12b right now (11434 normally, 11435
# when the fallback is in use); _ACTIVE_OLLAMA_URL is its chat URL.
_OLLAMA_MISSING = False
_LAST_HEAL_ERROR = None
_LAST_HEAL_AT = 0.0
_LAST_HEAL_RESULT = None
_LAST_FALLBACK_DIR = None
_LAST_FALLBACK_AT = 0.0
_OLLAMA_PROC = None
_ACTIVE_OLLAMA_PORT = OLLAMA_PRIMARY_PORT
_ACTIVE_OLLAMA_URL = _ollama_chat_url(OLLAMA_PRIMARY_PORT)
_HEAL_COOLDOWN_NO_MODEL = 60.0
_HEAL_COOLDOWN_START_FAILED = 15.0
_FALLBACK_COOLDOWN = 300.0

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

def _ollama_up(port=OLLAMA_PRIMARY_PORT, timeout=2):
    try:
        with urllib.request.urlopen(_ollama_root_url(port), timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _model_present(port=OLLAMA_PRIMARY_PORT, timeout=3):
    try:
        with urllib.request.urlopen(_ollama_tags_url(port), timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        for m in data.get("models", []):
            name = m.get("name", "")
            if name == MODEL or name.startswith(MODEL + ":"):
                return True
    except Exception:
        pass
    return False


def _resolve_brain_port():
    """The port whose Ollama lists gemma3:12b right now, or None.
    11434 first (normal path, unchanged); 11435 second (the fallback
    this server or Willow started). Never starts anything - it only
    reads /api/tags on each port."""
    global _ACTIVE_OLLAMA_PORT, _ACTIVE_OLLAMA_URL
    for port in (OLLAMA_PRIMARY_PORT, OLLAMA_FALLBACK_PORT):
        if _model_present(port):
            _ACTIVE_OLLAMA_PORT = port
            _ACTIVE_OLLAMA_URL = _ollama_chat_url(port)
            return port
    return None


def _resolve_brain_url():
    port = _resolve_brain_port()
    return _ollama_chat_url(port) if port else None


def _ollama_env(models_dir, port=None):
    env = dict(os.environ)
    env["OLLAMA_MODELS"] = models_dir
    env["OLLAMA_KEEP_ALIVE"] = "-1"
    if port is not None:
        # OLLAMA_HOST is how a second Ollama listens on 11435 instead
        # of the default 11434. Without it a second serve would fight
        # the stuck one for 11434 and lose.
        env["OLLAMA_HOST"] = "127.0.0.1:%d" % port
    return env


def _ollama_cmd():
    """The ollama command to run. Normally just ["ollama", "serve"].
    OLLAMA_CMD (space-separated) is a test hook so a fake Ollama can
    be substituted in a simulation; it is never set on the real PC."""
    override = os.environ.get("OLLAMA_CMD")
    if override:
        return override.split()
    return ["ollama", "serve"]


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


def _parse_netstat_owner(text, port):
    """Parse Windows `netstat -ano` output; return the PID listening on
    port, or None. Checks every way Ollama can listen: 127.0.0.1:port,
    0.0.0.0:port, [::]:port and [::1]:port. The old parser only knew
    127.0.0.1, so an Ollama bound to [::] looked ownerless and its
    port looked unkillable-for-no-reason. Unit-testable: the text is
    the only input."""
    want = {"127.0.0.1:%d" % port, "0.0.0.0:%d" % port,
            "[::]:%d" % port, "[::1]:%d" % port}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        if parts[0] != "TCP":
            continue
        if parts[1] in want and parts[3] == "LISTENING":
            try:
                return int(parts[4])
            except ValueError:
                return None
    return None


def _parse_tasklist_ollama_pids(text):
    """Parse Windows `tasklist /FO CSV /NH` output; return the PIDs of
    every ollama.exe. Unit-testable: the text is the only input."""
    pids = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('"'):
            continue
        fields = [f.strip('"') for f in line.split('","')]
        if len(fields) >= 2 and fields[0].lower() == "ollama.exe":
            try:
                pids.append(int(fields[1]))
            except ValueError:
                continue
    return pids


def _ollama_pids():
    """Every ollama.exe PID on this PC, or [] if it cannot be told.
    Windows: hidden tasklist. Linux: /proc cmdlines naming ollama."""
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq ollama.exe", "/FO", "CSV", "/NH"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=10, text=True)
            return _parse_tasklist_ollama_pids(out.stdout or "")
        except Exception:
            return []
    pids = []
    try:
        for pid in [x for x in os.listdir("/proc") if x.isdigit()]:
            try:
                with open("/proc/" + pid + "/cmdline", "rb") as f:
                    cmd = f.read().decode("utf-8", "replace")
            except OSError:
                continue
            if "ollama" in cmd:
                pids.append(int(pid))
    except Exception:
        pass
    return pids


def _port_owner_via_net_tcp_connection(port):
    """Windows fallback: Get-NetTCPConnection -LocalPort <port> gives
    the OwningProcess directly, even when netstat's text parse finds
    nothing. Hidden PowerShell, output captured. Returns the PID or
    None. Linux: None (the /proc path in _port_owner_pid covers it)."""
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetTCPConnection -LocalPort %d -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess" % port],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=10, text=True)
        text = (out.stdout or "").strip()
        if text:
            return int(text.split()[0])
    except Exception:
        pass
    return None


def _diagnose_port_owner(port):
    """Log who holds a port, with the evidence, and return the plain
    description. Tries netstat (IPv4 + IPv6), then
    Get-NetTCPConnection, then lists every ollama.exe PID. This is
    diagnostics only: nothing here kills anything, and a port whose
    owner cannot be determined is reported as exactly that - the
    11435 fallback must work even then. Nothing is ever killed on
    the strength of this diagnosis."""
    owner = _port_owner_pid(port)
    image = _pid_image_name(owner) if owner else None
    pids = _ollama_pids()
    if owner:
        msg = ("port %d is held by PID %d%s; ollama.exe PIDs on this PC: %s"
               % (port, owner, (" (" + image + ")") if image else "",
                  ", ".join(str(x) for x in pids) if pids else "none"))
    else:
        msg = ("port %d is held but its owner could not be determined "
               "(netstat IPv4/IPv6 and Get-NetTCPConnection found nothing); "
               "ollama.exe PIDs on this PC: %s"
               % (port, ", ".join(str(x) for x in pids) if pids else "none"))
    _log("Port owner diagnosis: " + msg + ". The stuck server is left alone; the 11435 fallback is used instead.")
    return msg


def _parse_proc_net_tcp_owner(text, port):
    """Parse Linux /proc/net/tcp text; return the inode of the socket
    LISTENING on 127.0.0.1:port, or None. 127.0.0.1 is 0100007F in
    little-endian hex; the port is hex; state 0A is LISTEN."""
    want_ip = "0100007F"
    want_port = "%04X" % port
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 10 or ":" not in parts[1]:
            continue
        ip, prt = parts[1].split(":")
        if ip == want_ip and prt == want_port and parts[3] == "0A":
            try:
                return int(parts[9])
            except ValueError:
                return None
    return None


def _port_owner_pid(port):
    """The PID of the process listening on port, or None if it
    cannot be determined. Windows: hidden netstat -ano (IPv4 and IPv6
    listeners), falling back to Get-NetTCPConnection -LocalPort, which
    gives the OwningProcess directly when netstat's text parse finds
    nothing. Linux: the listening socket's inode from /proc/net/tcp,
    matched to a process through /proc/<pid>/fd. Best effort - None
    just means 'cannot tell', never 'nobody'."""
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["netstat", "-ano"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=10, text=True)
            pid = _parse_netstat_owner(out.stdout or "", port)
            if pid is not None:
                return pid
        except Exception:
            pass
        return _port_owner_via_net_tcp_connection(port)
    try:
        with open("/proc/net/tcp", encoding="utf-8") as f:
            inode = _parse_proc_net_tcp_owner(f.read(), port)
    except Exception:
        return None
    if inode is None:
        return None
    want = "socket:[%d]" % inode
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except Exception:
        return None
    for pid in pids:
        try:
            for fd in os.listdir("/proc/" + pid + "/fd"):
                try:
                    if os.readlink("/proc/" + pid + "/fd/" + fd) == want:
                        return int(pid)
                except OSError:
                    continue
        except OSError:
            continue
    return None


def _pid_image_name(pid):
    """The image/command of a PID, or None. Windows: hidden tasklist.
    Linux: /proc/<pid>/cmdline."""
    if pid is None:
        return None
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=10, text=True)
            line = (out.stdout or "").strip()
            if line.startswith('"'):
                return line.split('"')[1]
        except Exception:
            pass
        return None
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            raw = f.read()
        parts = [p for p in raw.split(b"\x00") if p]
        if parts:
            return parts[0].decode("utf-8", "replace")
    except Exception:
        pass
    return None


def _pid_alive(pid):
    """True if the PID exists right now."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


_VERIFY_CACHE = {}


def _manifest_digests(models_dir):
    """Read the gemma3:12b manifest in a model folder. Returns
    (digests, error): digests is a list of (digest, expected_size) for
    the config and every layer, error is None on success or a plain
    reason the manifest could not be read."""
    manifest = os.path.join(
        models_dir, "manifests", "registry.ollama.ai",
        "library", "gemma3", "12b")
    try:
        with open(manifest, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return None, "manifest unreadable (%s)" % e
    digests = []
    try:
        cfg = data.get("config", {})
        if cfg.get("digest"):
            digests.append((cfg["digest"], int(cfg.get("size", 0))))
        for layer in data.get("layers", []):
            if layer.get("digest"):
                digests.append((layer["digest"], int(layer.get("size", 0))))
    except Exception as e:
        return None, "manifest unreadable (%s)" % e
    if not digests:
        return None, "manifest names no blobs"
    return digests, None


def _verify_blob(models_dir, digest, expected_size):
    """Verify ONE blob: it must exist, its size must match the manifest,
    and its SHA-256 must match its digest. Returns (ok, detail) - the
    detail names the exact failure (missing, wrong size, wrong hash)."""
    name = digest.split(":", 1)[-1]
    blob = os.path.join(models_dir, "blobs", "sha256-" + name)
    try:
        actual_size = os.path.getsize(blob)
    except OSError:
        return False, "blob %s is missing" % digest
    if actual_size != expected_size:
        return False, ("blob %s is %d bytes, manifest says %d "
                       "(truncated or wrong file)" % (digest, actual_size, expected_size))
    h = hashlib.sha256()
    try:
        with open(blob, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError as e:
        return False, "blob %s unreadable (%s)" % (digest, e)
    if h.hexdigest() != name:
        return False, ("blob %s hashes to %s, not its digest "
                       "(corrupt copy)" % (digest, h.hexdigest()))
    return True, "ok"


def _verify_model_dir(models_dir):
    """Strict check of one model folder: the manifest must read AND
    EVERY blob it names must exist, match its size, and match its
    SHA-256. A half-moved or truncated copy fails here - Ollama would
    reject it too, so the folder does not count. Returns (ok, failures):
    failures is a list of plain reasons, empty when the folder is good.
    Results are cached per folder fingerprint (manifest + blob sizes
    and mtimes), so an 8 GB hash is not redone on every Send."""
    digests, err = _manifest_digests(models_dir)
    if err:
        return False, ["manifest: " + err]
    try:
        manifest = os.path.join(
            models_dir, "manifests", "registry.ollama.ai",
            "library", "gemma3", "12b")
        st = os.stat(manifest)
        fingerprint = [st.st_size, st.st_mtime_ns]
        for digest, _size in digests:
            name = digest.split(":", 1)[-1]
            blob = os.path.join(models_dir, "blobs", "sha256-" + name)
            try:
                bst = os.stat(blob)
                fingerprint.append((bst.st_size, bst.st_mtime_ns))
            except OSError:
                fingerprint.append(None)
        key = (models_dir, tuple(fingerprint))
    except Exception:
        key = None
    if key is not None and key in _VERIFY_CACHE:
        return _VERIFY_CACHE[key]
    failures = []
    for digest, size in digests:
        ok, detail = _verify_blob(models_dir, digest, size)
        if not ok:
            failures.append(detail)
    result = (not failures, failures)
    if key is not None:
        _VERIFY_CACHE[key] = result
    return result


def _scan_model_dirs():
    """Check every candidate model folder with the strict verifier.
    Checks the env OLLAMA_MODELS first, then the EMMA_MODEL_DIRS
    override (os.pathsep-separated, a test hook), then D:, then C:.
    Returns (found_dir, report): found_dir is the first folder that is
    complete and verified, or None; report is a list of plain lines
    naming each folder checked and, for the rejected ones, exactly
    which blobs failed and why. The report is what the chat error
    shows when no folder is complete."""
    candidates = []
    env_dir = os.environ.get("OLLAMA_MODELS")
    if env_dir and env_dir not in candidates:
        candidates.append(env_dir)
    override = os.environ.get("EMMA_MODEL_DIRS")
    if override:
        for d in override.split(os.pathsep):
            if d and d not in candidates:
                candidates.append(d)
    for d in MODEL_DIRS:
        if d not in candidates:
            candidates.append(d)
    report = []
    for d in candidates:
        ok, failures = _verify_model_dir(d)
        if ok:
            report.append("%s: complete and verified" % d)
            return d, report
        if failures:
            report.append("%s: %s" % (d, " | ".join(failures)))
        else:
            report.append("%s: no complete model here" % d)
    return None, report


def _log_scan_report(report):
    """Write the folder scan report to the log, so a rejected folder and
    its exact failing blobs are always visible there."""
    for line in report:
        if "complete and verified" in line:
            _log("Model folder: " + line)
        else:
            _log("Model folder rejected: " + line)


def _model_in_dir(models_dir):
    """True if the given model folder holds a COMPLETE, VERIFIED
    gemma3:12b: the manifest AND every blob it names, each blob's size
    matching the manifest and its SHA-256 matching its digest. Ollama
    keeps one manifest per model under manifests/registry.ollama.ai/
    library/<name>/<tag>, and the blobs under blobs/sha256-<hex>.
    A manifest with missing, truncated, or corrupt blobs is not a
    model - it is a half-moved or half-downloaded one, and starting a
    fallback Ollama from that folder buys nothing, so it counts as not found."""
    ok, _failures = _verify_model_dir(models_dir)
    return ok


def _find_model_dir():
    """Find the model folder on disk that actually holds a complete,
    verified gemma3:12b. Returns the folder, or None. Kept for the
    /api/status route; the heal uses _scan_model_dirs so it can name
    the exact failures when no folder is complete."""
    found, _report = _scan_model_dirs()
    return found


def _start_ollama_on_port(models_dir, port=OLLAMA_FALLBACK_PORT):
    """Start a SECOND Ollama on the given port (11435) from the given
    verified model folder, and PROVE it took over: the server on that
    port must list gemma3:12b. Hidden: CREATE_NO_WINDOW, so no console
    window ever flashes. The child's stderr goes to
    phi-emma-local.log (never to pythonw's None streams), so a real
    failure is visible. The process is kept in _OLLAMA_PROC.

    The Ollama on 11434 is never touched here - not stopped, not
    killed, not restarted. If another process already holds this
    port (Willow started the same 11435 fallback first), this start
    may fail to bind; that is fine, because the wait below then sees
    the other server listing the model and counts as success. Both
    Emma and Willow check "is 11435 already up with the model?" first,
    so they never start a second 11435 and never fight. Returns
    (ok, detail)."""
    global _OLLAMA_MISSING, _OLLAMA_PROC
    try:
        err = open(LOG_FILE, "ab")
    except Exception:
        err = subprocess.DEVNULL
    try:
        proc = subprocess.Popen(
            _ollama_cmd(), env=_ollama_env(models_dir, port=port),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL, stderr=err)
    except FileNotFoundError:
        _OLLAMA_MISSING = True
        _log("Could not start Ollama: the ollama command was not found on PATH.")
        try:
            err.close()
        except Exception:
            pass
        return False, "the ollama command was not found on PATH"
    except Exception as e:
        _log(f"Could not start Ollama on port {port} ({e}).")
        try:
            err.close()
        except Exception:
            pass
        return False, "could not start Ollama on port %d (%s)" % (port, e)
    try:
        err.close()
    except Exception:
        pass
    _OLLAMA_PROC = proc
    for _ in range(30):
        if _model_present(port, timeout=3):
            _log(f"Ollama on port {port} lists gemma3:12b from {models_dir}.")
            return True, "Ollama on port %d lists gemma3:12b from %s" % (port, models_dir)
        if proc.poll() is not None:
            # The child died. If another server now lists the model on
            # this port (Willow's 11435, started first), that still
            # counts - the brain is there, whoever started it.
            if _model_present(port, timeout=3):
                _log(f"Ollama on port {port} lists gemma3:12b (started by another process).")
                return True, "Ollama on port %d lists gemma3:12b" % port
            _log(f"Ollama serve on port {port} exited at once (code {proc.returncode}). "
                 "See the tail of phi-emma-local.log for its own error.")
            return False, "Ollama serve on port %d exited at once (code %s)" % (port, proc.returncode)
        time.sleep(1)
    if _model_present(port, timeout=3):
        return True, "Ollama on port %d lists gemma3:12b from %s" % (port, models_dir)
    _log(f"Ollama on port {port} started but does not list gemma3:12b after 30s; stopping it.")
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    return False, "Ollama on port %d started but does not list gemma3:12b after 30s" % port


def _wait_ollama_model(port=OLLAMA_PRIMARY_PORT, timeout=30):
    """Wait up to timeout seconds for the Ollama on port to answer AND
    have the model. Deadline-based, so a slow /api/tags cannot stretch
    the wait."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _ollama_up(port, timeout=2) and _model_present(port, timeout=3):
            return True
        time.sleep(1)
    return _ollama_up(port, timeout=2) and _model_present(port, timeout=3)


_ENSURE_LOCK = threading.Lock()


def _ensure_ollama():
    """Make sure the SHARED local brain is answering AND has gemma3:12b.
    Willow and Emma share this one brain - the same gemma3:12b, served
    from whichever Ollama lists it.

    The model is already on this PC; the serving Ollama just cannot see
    it, because it was started pointing at a folder that does not hold
    it. So this heal FINDS the model on disk instead of downloading it
    again. There is no download anywhere in this file. The scan
    verifies EVERY blob (size and SHA-256), so a truncated copy is
    rejected and named, never started from.
    - 11434 lists the model: nothing to do (normal path, unchanged).
    - 11435 already lists the model (Willow started the fallback
      first): nothing to do - use 11435, start nothing.
    - Neither lists it: scan the folders for a complete, verified
      copy. If a folder has it, start a SECOND Ollama on 11435 from
      that folder - and PROVE it lists the model. The Ollama on 11434
      is never killed, never restarted, never fought: it was tried,
      it does not die (its port never frees, its owner cannot be
      determined), so it is left alone, idle. If the 11435 start
      fails, say exactly which step failed - do not pretend it
      worked. If no folder has a complete copy, say so plainly
      (which folders, which blobs) and stop - a start buys nothing
      and a download is never attempted.
    - Ollama down entirely: same 11435 start from the folder the
      scan found (or D: by default, verified first).
    A 11435 start is never repeated for the same folder within five
    minutes when it started and still did not help, and a "not on
    disk" verdict is not rescanned for a minute - so pressing Send
    cannot start Ollama over and over. A FAILED start is not cooled
    down: the next Send can try again. Never fatal and never blocks
    the server from answering: the page answers from second zero and
    the chat route reports the true state."""
    global _LAST_HEAL_ERROR, _LAST_HEAL_AT, _LAST_HEAL_RESULT
    global _LAST_FALLBACK_DIR, _LAST_FALLBACK_AT
    global _ACTIVE_OLLAMA_PORT, _ACTIVE_OLLAMA_URL
    with _ENSURE_LOCK:
        now = time.time()
        if _resolve_brain_port() is not None:
            _LAST_HEAL_ERROR = None
            _LAST_HEAL_RESULT = "ready"
            return True
        if _LAST_HEAL_RESULT == "no_model_on_disk" and now - _LAST_HEAL_AT < _HEAL_COOLDOWN_NO_MODEL:
            return False
        if _LAST_HEAL_RESULT == "start_failed" and now - _LAST_HEAL_AT < _HEAL_COOLDOWN_START_FAILED:
            return False
        _LAST_HEAL_AT = now
        _LAST_HEAL_ERROR = None
        if _ollama_up(OLLAMA_PRIMARY_PORT, timeout=2):
            # 11434 is up but does not list the model. Diagnose who
            # holds it (for the log only), then leave it alone.
            _diagnose_port_owner(OLLAMA_PRIMARY_PORT)
            _log("Ollama on 11434 is up but gemma3:12b is not in it. "
                 "Leaving 11434 alone; the fallback on 11435 will serve the brain.")
        found, report = _scan_model_dirs()
        _log_scan_report(report)
        if found is None:
            _LAST_HEAL_ERROR = (
                "gemma3:12b is not complete in either model folder. "
                + " | ".join(report) + ". I never download.")
            _LAST_HEAL_RESULT = "no_model_on_disk"
            _log("Neither Ollama lists gemma3:12b, and the model is in "
                 "neither model folder on disk. Not starting a fallback, "
                 "not downloading.")
            return False
        if found == _LAST_FALLBACK_DIR and now - _LAST_FALLBACK_AT < _FALLBACK_COOLDOWN:
            _LAST_HEAL_ERROR = (
                "A second Ollama was already started on 11435 from " + found +
                " and gemma3:12b still is not in it.")
            _LAST_HEAL_RESULT = "fallback_no_help"
            return False
        _log("gemma3:12b is on disk at " + found +
             ". Starting a second Ollama on 11435 from there; 11434 is left alone.")
        ok, detail = _start_ollama_on_port(found, OLLAMA_FALLBACK_PORT)
        if not ok:
            _LAST_HEAL_ERROR = "The second Ollama on 11435 could not be started: " + detail
            _LAST_HEAL_RESULT = "start_failed"
            _log("The 11435 fallback did not come up: " + detail)
            return False
        _LAST_FALLBACK_DIR = found
        _LAST_FALLBACK_AT = time.time()
        if _wait_ollama_model(OLLAMA_FALLBACK_PORT, 30):
            _ACTIVE_OLLAMA_PORT = OLLAMA_FALLBACK_PORT
            _ACTIVE_OLLAMA_URL = _ollama_chat_url(OLLAMA_FALLBACK_PORT)
            _LAST_HEAL_RESULT = "ready"
            _log("The brain is back on 11435 from the folder that holds gemma3:12b.")
            return True
        _LAST_HEAL_ERROR = (
            "A second Ollama was started on 11435 from " + found +
            " and the model still is not in it, even though the folder "
            "was verified complete.")
        _LAST_HEAL_RESULT = "fallback_no_help"
        _log("gemma3:12b is still missing after starting the 11435 fallback from "
             + found + ".")
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
    the fallback Ollama is started or the model is found."""
    global _HEAL_RUNNING
    with _HEAL_LOCK:
        if _HEAL_RUNNING:
            return False
        _HEAL_RUNNING = True
    threading.Thread(target=_heal_worker, daemon=True).start()
    return True

def _ollama_chat(messages, num_predict=377, url=None):
    """One chat turn against local Ollama. Returns the reply text.
    Raises RuntimeError with a plain reason on any failure. The URL
    is the resolved brain URL (11434 normally, 11435 when the
    fallback is serving the brain); when none is given it is resolved
    fresh, so a chat never talks to the stuck 11434 by default."""
    if url is None:
        url = _resolve_brain_url() or _ACTIVE_OLLAMA_URL
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
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=600)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            body = ""
        raise RuntimeError(
            f"Ollama {url} said HTTP {e.code} for model {MODEL}: {body}")
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
            brain_port = _resolve_brain_port()
            self._send_json(200, {
                "ok": True,
                "local": True,
                "nuance": False,
                "model": MODEL,
                "ollama_up": _ollama_up(OLLAMA_PRIMARY_PORT, timeout=2),
                "model_present": _model_present(OLLAMA_PRIMARY_PORT, timeout=3),
                "ollama_primary_up": _ollama_up(OLLAMA_PRIMARY_PORT, timeout=2),
                "model_present_primary": _model_present(OLLAMA_PRIMARY_PORT, timeout=3),
                "ollama_fallback_up": _ollama_up(OLLAMA_FALLBACK_PORT, timeout=2),
                "model_present_fallback": _model_present(OLLAMA_FALLBACK_PORT, timeout=3),
                "active_ollama_port": brain_port,
                "active_ollama_url": _ollama_chat_url(brain_port) if brain_port else None,
                "model_dir": _find_model_dir(),
                "model_dirs_checked": list(MODEL_DIRS),
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
        # Fast check only - never block the reply on the heal. The heal
        # runs in a background thread (see main); this route just reports
        # whether the brain is ready right now and kicks the heal if not.
        # The brain is ready when EITHER Ollama lists the model: 11434
        # normally, 11435 when the fallback is serving it. The old code
        # only checked 11434, so a working 11435 brain still got a 503.
        # The errors name the true state and never tell Tyree to start
        # Ollama, check a folder, or download anything himself - the
        # server brings the brain back on its own.
        brain_url = _resolve_brain_url()
        if not brain_url:
            _kick_heal()
            if _OLLAMA_MISSING:
                self._send_json(503, {"error": "Her brain cannot start: the Ollama program was not found on this PC. The detail is in phi-emma-local.log."})
            elif not _ollama_up(OLLAMA_PRIMARY_PORT, timeout=2) and not _ollama_up(OLLAMA_FALLBACK_PORT, timeout=2):
                self._send_json(503, {"error": "Her brain is not running yet - I am bringing it back now. Send again in a moment."})
            elif _LAST_HEAL_ERROR:
                self._send_json(503, {"error": f"Her brain could not be brought back ({_LAST_HEAL_ERROR}). The detail is in phi-emma-local.log - Send again and I will try once more."})
            elif _HEAL_RUNNING:
                self._send_json(503, {"error": "Her brain is not in the Ollama that is running yet. I am bringing up a second Ollama from the folder that has it - no need to check anything. Send again in a moment."})
            else:
                self._send_json(503, {"error": "Her brain is not in the Ollama that is running. I am bringing up a second Ollama from the folder that has it. Send again in a moment."})
            return
        try:
            reply = _ollama_chat(messages, num_predict=body.get("num_predict", 377), url=brain_url)
        except RuntimeError as e:
            _log(f"Chat failed ({e}); kicking the heal.")
            _kick_heal()
            self._send_json(502, {"error": "Her brain hiccuped - Send again in a moment."})
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
        # seconds (start Ollama, wait for the model) - during that whole
        # window nothing listened on 1620, so the browser got
        # ERR_CONNECTION_REFUSED and the flash's page retries could miss
        # it. Now the page answers from second zero; the brain heals in a
        # background thread and the chat route says plainly (503) until
        # it arrives. The heal finds the model on disk and never
        # downloads, and it never opens a console window, so no window
        # flashes when the page loads or when Tyree presses Send.
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
