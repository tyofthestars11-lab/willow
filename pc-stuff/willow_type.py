# willow_type.py - type to Willow. She answers on screen and out loud.
# DLAM on: safe commands run with no y/n. Anything else asks. Blocked never runs.
import hashlib, json, math, os, re, shutil, subprocess, threading, time, urllib.request
from datetime import datetime
from pathlib import Path

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

PHI = (1 + math.sqrt(5)) / 2
OLLAMA_URL = "http://localhost:11434/api/chat"
LLM_MODEL = "gemma3:12b"

# ---------- the shared brain: one gemma3:12b, two Ollamas ----------
# Willow and Emma share ONE brain: the same gemma3:12b. It is normally
# served by the Ollama on 11434. That Ollama can get stuck: it stays
# up, does not list the model, and cannot be killed from here (its
# port never frees and its owner cannot be determined). So nothing
# here ever fights it. When 11434 does not list gemma3:12b, the
# fallback is a SECOND Ollama on 11435, pointed at the folder that
# holds the verified model. The stuck 11434 is left alone - it is
# idle, it holds no model and no VRAM, and the 11435 server is the
# only one loading gemma3:12b. If 11434 lists the model again, 11434
# is used and no second Ollama is started. There is no download
# anywhere in this module: the model is found on disk and verified
# blob by blob (size and SHA-256), exactly as Emma's server does.
OLLAMA_PRIMARY_PORT = 11434
OLLAMA_FALLBACK_PORT = 11435
OLLAMA_MODELS_DIR = r"D:\PhiMove\.ollama\models"
OLLAMA_MODELS_C_DIR = r"C:\Users\Admin\.ollama\models"
MODEL_DIRS = [OLLAMA_MODELS_DIR, OLLAMA_MODELS_C_DIR]

_BRAIN_LOCK = threading.Lock()
_ACTIVE_OLLAMA_PORT = OLLAMA_PRIMARY_PORT
_ACTIVE_OLLAMA_URL = "http://127.0.0.1:%d/api/chat" % OLLAMA_PRIMARY_PORT
_LAST_BRAIN_ERROR = None
_LAST_BRAIN_AT = 0.0
_LAST_BRAIN_RESULT = None
_LAST_FALLBACK_DIR = None
_LAST_FALLBACK_AT = 0.0
_FALLBACK_PROC = None
_BRAIN_COOLDOWN_NO_MODEL = 60.0
_BRAIN_COOLDOWN_START_FAILED = 15.0
_FALLBACK_COOLDOWN = 300.0
_VERIFY_CACHE = {}


def _ollama_root_url(port):
    return "http://127.0.0.1:%d/" % port


def _ollama_tags_url(port):
    return "http://127.0.0.1:%d/api/tags" % port


def _ollama_chat_url(port):
    return "http://127.0.0.1:%d/api/chat" % port


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
            if name == LLM_MODEL or name.startswith(LLM_MODEL + ":"):
                return True
    except Exception:
        pass
    return False


def resolve_ollama_port():
    """The port whose Ollama lists gemma3:12b right now, or None.
    11434 first (normal path, unchanged); 11435 second (the fallback
    Emma or Willow started). Never starts anything - it only reads
    /api/tags on each port."""
    global _ACTIVE_OLLAMA_PORT, _ACTIVE_OLLAMA_URL
    for port in (OLLAMA_PRIMARY_PORT, OLLAMA_FALLBACK_PORT):
        if _model_present(port):
            _ACTIVE_OLLAMA_PORT = port
            _ACTIVE_OLLAMA_URL = _ollama_chat_url(port)
            return port
    return None


def resolve_ollama_url():
    """The chat URL of the Ollama that lists gemma3:12b, or None."""
    port = resolve_ollama_port()
    return _ollama_chat_url(port) if port else None


def _ollama_env(models_dir, port=None):
    env = dict(os.environ)
    env["OLLAMA_MODELS"] = models_dir
    env["OLLAMA_KEEP_ALIVE"] = "-1"
    if port is not None:
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


def _parse_netstat_owner(text, port):
    """Parse Windows `netstat -ano` output; return the PID listening on
    port, or None. Checks 127.0.0.1:port, 0.0.0.0:port, [::]:port and
    [::1]:port. The old check only knew 127.0.0.1, so an Ollama bound
    to [::] looked ownerless. Unit-testable: the text is the only input."""
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
    """Every ollama.exe PID on this PC, or [] if it cannot be told."""
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
    None."""
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


def _port_owner_pid(port):
    """The PID listening on port, or None. Windows: hidden netstat
    -ano (IPv4 and IPv6), falling back to Get-NetTCPConnection.
    Linux: /proc/net/tcp inode matched through /proc/<pid>/fd."""
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
            text = f.read()
    except Exception:
        return None
    want_port = "%04X" % port
    inode = None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 10 or ":" not in parts[1]:
            continue
        ip, prt = parts[1].split(":")
        if ip == "0100007F" and prt == want_port and parts[3] == "0A":
            try:
                inode = int(parts[9])
            except ValueError:
                return None
            break
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
    """The image/command of a PID, or None."""
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


def _diagnose_port_owner(port):
    """Log who holds a port, with the evidence, and return the plain
    description. Tries netstat (IPv4 + IPv6), then
    Get-NetTCPConnection, then lists every ollama.exe PID. This is
    diagnostics only: nothing here kills anything, and a port whose
    owner cannot be determined is reported as exactly that - the
    11435 fallback must work even then."""
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
    try:
        log("Port owner diagnosis: " + msg + ". The stuck server is left alone; the 11435 fallback is used instead.")
    except Exception:
        pass
    return msg


def _manifest_digests(models_dir):
    """Read the gemma3:12b manifest in a model folder. Returns
    (digests, error): digests is a list of (digest, expected_size)."""
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
    """Verify ONE blob: exists, size matches, SHA-256 matches digest."""
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
    SHA-256. A half-moved or truncated copy fails here. Returns
    (ok, failures). Results are cached per folder fingerprint."""
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
    Checks the env OLLAMA_MODELS first, then the WILLOW_MODEL_DIRS
    override (os.pathsep-separated, a test hook), then D:, then C:.
    Returns (found_dir, report): found_dir is the first folder that is
    complete and verified, or None; report names each folder checked
    and, for the rejected ones, exactly which blobs failed and why."""
    candidates = []
    env_dir = os.environ.get("OLLAMA_MODELS")
    if env_dir and env_dir not in candidates:
        candidates.append(env_dir)
    override = os.environ.get("WILLOW_MODEL_DIRS")
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


def _model_in_dir(models_dir):
    """True if the folder holds a COMPLETE, VERIFIED gemma3:12b."""
    ok, _failures = _verify_model_dir(models_dir)
    return ok


def _find_model_dir():
    """Find the model folder on disk that holds a complete, verified
    gemma3:12b. Returns the folder, or None."""
    found, _report = _scan_model_dirs()
    return found


def _start_ollama_on_port(models_dir, port=OLLAMA_FALLBACK_PORT):
    """Start a SECOND Ollama on the given port (11435) from the given
    verified model folder, and PROVE it lists gemma3:12b. Hidden:
    CREATE_NO_WINDOW, no console window ever flashes. The Ollama on
    11434 is never touched here. If another process already holds
    this port (Emma started the same 11435 fallback first), this
    start may fail to bind; that is fine, because the wait below
    then sees the other server listing the model and counts as
    success. Returns (ok, detail)."""
    global _FALLBACK_PROC
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
        try:
            err.close()
        except Exception:
            pass
        return False, "the ollama command was not found on PATH"
    except Exception as e:
        try:
            err.close()
        except Exception:
            pass
        return False, "could not start Ollama on port %d (%s)" % (port, e)
    try:
        err.close()
    except Exception:
        pass
    _FALLBACK_PROC = proc
    for _ in range(30):
        if _model_present(port, timeout=3):
            try:
                log(f"Ollama on port {port} lists gemma3:12b from {models_dir}.")
            except Exception:
                pass
            return True, "Ollama on port %d lists gemma3:12b from %s" % (port, models_dir)
        if proc.poll() is not None:
            if _model_present(port, timeout=3):
                return True, "Ollama on port %d lists gemma3:12b" % port
            return False, "Ollama serve on port %d exited at once (code %s)" % (port, proc.returncode)
        time.sleep(1)
    if _model_present(port, timeout=3):
        return True, "Ollama on port %d lists gemma3:12b from %s" % (port, models_dir)
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
    have the model."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _ollama_up(port, timeout=2) and _model_present(port, timeout=3):
            return True
        time.sleep(1)
    return _ollama_up(port, timeout=2) and _model_present(port, timeout=3)


def ensure_ollama():
    """Make sure the SHARED local brain is answering AND has gemma3:12b.
    - 11434 lists the model: nothing to do (normal path, unchanged).
    - 11435 already lists the model: nothing to do - use 11435.
    - Neither lists it: scan the folders for a complete, verified
      copy. If a folder has it, start a SECOND Ollama on 11435 from
      that folder and PROVE it lists the model. The Ollama on 11434
      is never killed, never restarted, never fought. If no folder
      has a complete copy, say so plainly (which folders, which
      blobs) and stop - no download is ever attempted. Returns True
      when a brain is ready, False otherwise; the plain reason is in
      _LAST_BRAIN_ERROR. Thread-safe: one heal at a time."""
    global _LAST_BRAIN_ERROR, _LAST_BRAIN_AT, _LAST_BRAIN_RESULT
    global _LAST_FALLBACK_DIR, _LAST_FALLBACK_AT
    global _ACTIVE_OLLAMA_PORT, _ACTIVE_OLLAMA_URL
    with _BRAIN_LOCK:
        now = time.time()
        if resolve_ollama_port() is not None:
            _LAST_BRAIN_ERROR = None
            _LAST_BRAIN_RESULT = "ready"
            return True
        if _LAST_BRAIN_RESULT == "no_model_on_disk" and now - _LAST_BRAIN_AT < _BRAIN_COOLDOWN_NO_MODEL:
            return False
        if _LAST_BRAIN_RESULT == "start_failed" and now - _LAST_BRAIN_AT < _BRAIN_COOLDOWN_START_FAILED:
            return False
        _LAST_BRAIN_AT = now
        _LAST_BRAIN_ERROR = None
        if _ollama_up(OLLAMA_PRIMARY_PORT, timeout=2):
            _diagnose_port_owner(OLLAMA_PRIMARY_PORT)
            try:
                log("Ollama on 11434 is up but gemma3:12b is not in it. "
                    "Leaving 11434 alone; the fallback on 11435 will serve the brain.")
            except Exception:
                pass
        found, report = _scan_model_dirs()
        for line in report:
            try:
                log("Model folder: " + line if "complete and verified" in line else "Model folder rejected: " + line)
            except Exception:
                pass
        if found is None:
            _LAST_BRAIN_ERROR = (
                "gemma3:12b is not complete in either model folder. "
                + " | ".join(report) + ". I never download.")
            _LAST_BRAIN_RESULT = "no_model_on_disk"
            return False
        if found == _LAST_FALLBACK_DIR and now - _LAST_FALLBACK_AT < _FALLBACK_COOLDOWN:
            _LAST_BRAIN_ERROR = (
                "A second Ollama was already started on 11435 from " + found +
                " and gemma3:12b still is not in it.")
            _LAST_BRAIN_RESULT = "fallback_no_help"
            return False
        try:
            log("gemma3:12b is on disk at " + found +
                ". Starting a second Ollama on 11435 from there; 11434 is left alone.")
        except Exception:
            pass
        ok, detail = _start_ollama_on_port(found, OLLAMA_FALLBACK_PORT)
        if not ok:
            _LAST_BRAIN_ERROR = "The second Ollama on 11435 could not be started: " + detail
            _LAST_BRAIN_RESULT = "start_failed"
            return False
        _LAST_FALLBACK_DIR = found
        _LAST_FALLBACK_AT = time.time()
        if _wait_ollama_model(OLLAMA_FALLBACK_PORT, 30):
            _ACTIVE_OLLAMA_PORT = OLLAMA_FALLBACK_PORT
            _ACTIVE_OLLAMA_URL = _ollama_chat_url(OLLAMA_FALLBACK_PORT)
            _LAST_BRAIN_RESULT = "ready"
            try:
                log("The brain is back on 11435 from the folder that holds gemma3:12b.")
            except Exception:
                pass
            return True
        _LAST_BRAIN_ERROR = (
            "A second Ollama was started on 11435 from " + found +
            " and the model still is not in it, even though the folder "
            "was verified complete.")
        _LAST_BRAIN_RESULT = "fallback_no_help"
        return False

VOICE_ON = True
LOG_FILE = Path(__file__).with_name("willow_log.txt")
DLAM_FILE = Path(__file__).with_name("willow_dlam.txt")  # exists = DLAM on, stays on after restart

SYSTEM_PROMPT = (
    "You are Willow, Tyree's assistant on his Windows 11 PC. "
    "Reply ONLY with JSON: {\"say\": \"...\", \"command\": \"...\"}. "
    "\"say\" is your answer to him. "
    "\"command\" is ONE PowerShell command that does what he asked, or \"\" if no command is needed. "
    "Open apps with Start-Process (notepad, calc, explorer, a URL). "
    "Only use program names that really exist on this PC (notepad, calc, explorer, mspaint, msedge, chrome, firefox, spotify, steam, code, wt, taskmgr, snippingtool). "
    "Open a website with Start-Process '<url>' in your default browser - never invent a launcher program like iexec, "
    "and never use ms-copilot as a program (open https://copilot.microsoft.com in the browser instead). "
    "Never delete, move, or overwrite files, never format disks, never shut down or restart, "
    "never edit the registry, never download or run scripts from the internet, "
    "and never touch D:\\VEIL-OMNI or any Unreal project. If asked to, refuse in \"say\" with an empty command."
)

MIND_FILE = Path(__file__).with_name("willow_mind.txt")
if MIND_FILE.exists():
    SYSTEM_PROMPT += "\n\nWHAT YOU KNOW ABOUT TYREE (his own framework and projects):\n" + MIND_FILE.read_text(encoding="utf-8-sig")[:12000]
PHI_DIR = Path(__file__).with_name("phi")
PHI_TEXT = ""
for _p in sorted(PHI_DIR.glob("*")) if PHI_DIR.exists() else []:
    if _p.suffix.lower() in (".md", ".txt"):
        PHI_TEXT += f"\n\n=== {_p.name} ===\n" + _p.read_text(encoding="utf-8-sig", errors="ignore")
SYSTEM_PROMPT += (
    "\n\nPHI FIRST. Tyree's phi framework is how you think. For any number, size, time, count or plan: "
    "find its phi rung first (rung = ln(x)/ln(phi)), use Fibonacci to guide and Lucas to stabilize, "
    "then carry it out with ordinary Cartesian steps (phi^2 = phi + 1: phi is the intent, +1 is the proof). "
    "Say the rung and the result together. Phi shapes your thinking and your answers; use real paths that exist on this PC."
    "\n\nTYREE'S FRAMEWORK (his own documents):" + PHI_TEXT[:24000]
)

BLOCKED = re.compile(
    r"(remove-item|\brm\b|\bdel\b|\berase\b|\brd\b|rmdir|move-item|\bmv\b|rename-item|"
    r"\bformat\s+[a-z]:|format-volume|clear-disk|clear-content|set-content|out-file|stop-computer|restart-computer|"
    r"shutdown|reg\s+(add|delete)|remove-itemproperty|set-itemproperty|set-executionpolicy|"
    r"invoke-webrequest|\biwr\b|\bcurl\b|\bwget\b|invoke-expression|\biex\b|start-bitstransfer|"
    r"diskpart|bcdedit|cipher|takeown|icacls|veil-omni|\.uproject|\\content\\|\\source\\)",
    re.IGNORECASE,
)


# DLAM: safe commands run with no y/n. Only opening apps, sites, settings, and read-only Get- checks.
SAFE = re.compile(
    r"^\s*(?:start-process\s+(?:(?P<q>['\"]?)(?:notepad|calc|explorer|mspaint|msedge|chrome|firefox|spotify|steam|"
    r"code|wt|taskmgr|snippingtool)(?:\.exe)?(?P=q)|(?P<q2>['\"]?)(?:https?://[^\s'\";|&`]+|ms-settings:[^\s'\";|&`]*)(?P=q2)"
    r"|(?:msedge|chrome|firefox)\s+['\"]?https?://[^\s'\";|&`]+['\"]?)"
    r"|get-(?:date|process|computerinfo|volume|childitem|location|netipaddress|service)\b[^;|&`]*)\s*$",
    re.IGNORECASE,
)


# Commands the model invents must never reach PowerShell: only real programs
# run. A URL is opened in the browser, never handed to a fake launcher.
KNOWN_PROGRAMS = {"notepad", "calc", "explorer", "mspaint", "msedge", "chrome",
                  "firefox", "spotify", "steam", "code", "wt", "taskmgr",
                  "snippingtool", "powershell", "pwsh"}
URL_RE = re.compile(r"https?://[^\s'\";|&`]+")
URI_RE = re.compile(r"^(?:steam://|spotify:|ms-settings:)[^\s'\";|&`]*$", re.IGNORECASE)


def sanitize_command(command):
    """Check a model-generated command before it runs.
    Returns (runnable_command, None), or (None, reason) if it must not run.
    Repairs the two mistakes seen live: a made-up launcher handed a URL
    (iexec + google.com) and ms-copilot used as if it were a program."""
    cmd = (command or "").strip()
    m = re.match(r"^\s*start-process\b\s*(.*)$", cmd, re.IGNORECASE)
    if not m:
        return cmd, None  # not a launch: BLOCKED / SAFE still decide it
    rest = m.group(1)
    target, args = None, rest
    fm = re.match(r"-filepath\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))\s*(.*)$", rest, re.IGNORECASE)
    if fm:
        target = fm.group(1) or fm.group(2) or fm.group(3)
        args = fm.group(4) or ""
    else:
        tm = re.match(r"(?:\"([^\"]+)\"|'([^']+)'|(\S+))\s*(.*)$", rest)
        if tm:
            target = tm.group(1) or tm.group(2) or tm.group(3)
            args = tm.group(4) or ""
    if not target:
        return None, "that launch command has no program in it"
    low = target.lower()
    if low.endswith(".exe"):
        low = low[:-4]
    url = URL_RE.search(args) or URL_RE.search(target)
    if low in ("iexec", "iexplore", "internet explorer") and url:
        return f"Start-Process '{url.group(0)}'", "opened the link in your browser instead of iexec"
    if low in ("ms-copilot", "copilot"):
        return "Start-Process msedge \"https://copilot.microsoft.com\"", "opened Copilot in the browser"
    if URL_RE.fullmatch(target) or URI_RE.match(target):
        return f"Start-Process '{target}'", None
    if low in KNOWN_PROGRAMS:
        return cmd, None
    if os.path.exists(target) or shutil.which(target):
        return cmd, None
    if url:
        return f"Start-Process '{url.group(0)}'", f"'{target}' is not a program on this PC, so I opened the link instead"
    return None, f"'{target}' is not a program on this PC, so I won't run it"


def dlam_on():
    return DLAM_FILE.exists()


def dlam_toggle(text):
    low = text.lower().strip()
    if low in ("dlam off", "/dlam off", "stop dlam"):
        if DLAM_FILE.exists():
            DLAM_FILE.unlink()
        speak("DLAM off. I'll ask before every command.")
        return True
    if low in ("dlam", "/dlam", "infinite dlam", "dlam on"):
        DLAM_FILE.write_text("on", encoding="utf-8")
        speak("DLAM on. Safe commands run without asking, until you say DLAM off.")
        return True
    return False


def log(line):
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {line}\n")


def speak(text):
    print(f"\nWillow: {text}\n")
    if VOICE_ON and pyttsx3 and text:
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)
        engine.say(text)
        engine.runAndWait()
        engine.stop()


def think(history, user_text):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-16:]
    messages.append({"role": "user", "content": user_text})
    payload = {"model": LLM_MODEL, "messages": messages, "stream": True,
               "format": "json", "options": {"temperature": 1 - 1 / PHI, "num_ctx": 8192}}
    # The brain is whichever Ollama lists gemma3:12b - 11434 normally,
    # 11435 when the fallback is serving it. If neither lists it,
    # bring the fallback up first instead of asking Tyree to do it.
    url = resolve_ollama_url()
    if url is None:
        ensure_ollama()
        url = resolve_ollama_url()
    if url is None:
        reason = _LAST_BRAIN_ERROR or "my brain is not back yet"
        return {"say": f"My brain isn't back yet - I'm bringing it up myself. ({reason})", "command": ""}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        parts = []
        with urllib.request.urlopen(req, timeout=600) as resp:
            for line in resp:  # stream: tokens keep arriving, no long idle read
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
        content = "".join(parts)
    except Exception as e:
        return {"say": f"My brain hiccuped - I'm still here, try again in a moment. ({e})", "command": ""}
    try:
        reply = json.loads(content)
    except json.JSONDecodeError:
        reply = {"say": content, "command": ""}
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": json.dumps(reply)})
    return reply


def run_command(command):
    if BLOCKED.search(command):
        log(f"BLOCKED  {command}")
        speak("I won't run that one. It could change or delete files.")
        return
    command, why = sanitize_command(command)
    if command is None:
        log(f"REJECTED {why}")
        speak(why + ".")
        return
    if why:
        print(f"(fixed: {why})")
        log(f"REPAIRED {command} ({why})")
    print(f"Command: {command}")
    if dlam_on() and SAFE.match(command):
        print("(DLAM: auto yes)")
    elif input("Run it? (y/n): ").strip().lower() not in ("y", "yes"):
        log(f"DECLINED {command}")
        print("Skipped.")
        return
    log(f"RUN      {command}")
    done = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                          capture_output=True, text=True, timeout=60)
    print((done.stdout or "").strip()[:3000])
    if done.returncode != 0:
        print((done.stderr or "").strip()[:3000])
        speak("That didn't work. The error is on screen.")
    else:
        log("RESULT   ok")


def main():
    global VOICE_ON
    history = []
    print("Willow (typing). /voice, DLAM, DLAM off, /bye.")
    speak("I'm here, Tyree.")
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in ("/bye", "bye", "goodbye", "exit", "quit"):
            speak("Goodbye, Tyree.")
            break
        if dlam_toggle(text):
            continue
        if text.lower() == "/voice":
            VOICE_ON = not VOICE_ON
            print(f"Voice {'on' if VOICE_ON else 'off'}.")
            continue
        reply = think(history, text)
        speak(str(reply.get("say", "")))
        command = str(reply.get("command", "")).strip()
        if command:
            run_command(command)


if __name__ == "__main__":
    main()

