# willow_widget.py — Willow as a floating desktop widget. F.R.I.D.A.Y. INFINITE.
# A gold phi bubble that lives on the desktop. Click it, talk to her — speak or type.
# She answers on screen AND out loud (local Kokoro voice), hears the mic (Whisper),
# and runs safe actions herself (DLAM). No browser, no port, no paid service, all local.
# Brain: local Ollama gemma3:12b through willow_web.ask (streaming, phi, live telemetry).
# Runs from the live folder next to her sisters (willow_web, willow_type, willow_ears...).
import json, os, queue, re, subprocess, sys, threading, time, urllib.request, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # her sisters live next to this file

# pythonw has no console: prints would crash threads. Send them to a log file.
def _quiet_stdio():
    try:
        if sys.stdout is None:
            sys.stdout = open(HERE / "willow_widget.log", "a", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(HERE / "willow_widget.log", "a", encoding="utf-8")
    except Exception:
        try:
            devnull = open(os.devnull, "w")
            if sys.stdout is None:
                sys.stdout = devnull
            if sys.stderr is None:
                sys.stderr = devnull
        except Exception:
            pass


_quiet_stdio()

import tkinter as tk

import willow_web as ww
import willow_eyes as we
import willow_launch as wl
import willow_telemetry
import willow_ears as we_ears

w = ww.w
w.LLM_MODEL = "gemma3:12b"  # bigger brain, same as the Command Center

# ---------- phi styling ----------
PHI = (1 + 5 ** 0.5) / 2
BG = "#060914"
PANEL = "#0b1226"
LINE = "#1d2b55"
GOLD = "#d8b25a"
GOLD2 = "#f3d98b"
CYAN = "#5ee7ff"
RED = "#ff5d6c"
GRN = "#41e39a"
TXT = "#dfe6ff"
DIM = "#7b88b3"
FONT = ("Consolas", 11)
FONT_B = ("Consolas", 11, "bold")
BUBBLE = 89            # Fibonacci — the bubble
CHAT_W, CHAT_H = 377, 610  # Fibonacci pair, 610 / 377 = phi

HISTORY = []
PENDING = []
VOICE = {"on": True}
UIQ = queue.Queue()
SPEAK_LOCK = threading.Lock()
LOCK_FILE = HERE / "willow_widget.lock"

APPS = {
    "steam": "Start-Process 'steam://open/main'", "notepad": "Start-Process notepad",
    "calculator": "Start-Process calc", "calc": "Start-Process calc",
    "task manager": "Start-Process taskmgr", "file explorer": "Start-Process explorer",
    "explorer": "Start-Process explorer", "paint": "Start-Process mspaint",
    "edge": "Start-Process msedge", "chrome": "Start-Process chrome", "firefox": "Start-Process firefox",
    "spotify": "Start-Process 'spotify:'", "vs code": "Start-Process code", "terminal": "Start-Process wt",
    "settings": "Start-Process 'ms-settings:'", "snipping tool": "Start-Process snippingtool",
    "copilot": "Start-Process msedge \"https://copilot.microsoft.com\"",
    "google": "Start-Process msedge \"https://www.google.com\"",
}


# ---------- one copy only ----------
def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _single_instance():
    try:
        if LOCK_FILE.exists():
            pid = int((LOCK_FILE.read_text(encoding="utf-8").strip() or "0"))
            if pid and _pid_alive(pid):
                return False
    except Exception:
        pass
    try:
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass
    return True


def _release_lock():
    try:
        if LOCK_FILE.exists() and LOCK_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            LOCK_FILE.unlink()
    except Exception:
        pass


# ---------- thread-safe say / status (UI thread renders, any thread may call) ----------
def say(text, who="Willow", voice=True):
    if text is None:
        return
    text = str(text)
    if not text:
        return
    UIQ.put(("say", who, text))
    if text.startswith("Ears on"):
        UIQ.put(("ears", "listening"))
    if "didn't start" in text and "ears" in text.lower():
        UIQ.put(("ears", "off"))
    if voice and VOICE["on"]:
        try:
            with SPEAK_LOCK:
                w.speak(text)
        except Exception:
            pass


def run_ps(command):
    w.log(f"RUN      {command}")
    done = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                          capture_output=True, text=True, timeout=60)
    out = ((done.stdout or "") + (done.stderr or "")).strip()[:1500]
    w.log("RESULT   " + ("ok" if done.returncode == 0 else "error"))
    return ("Done." if done.returncode == 0 else "That didn't work.") + (f"\n{out}" if out else "")


def handle_command(command):
    # Split "a; b" into steps. BLOCKED never runs. DLAM auto-runs SAFE steps.
    # Anything else waits for RUN / NO in the widget.
    steps = [s.strip() for s in command.split(";") if s.strip()]
    for s in steps:
        if w.BLOCKED.search(s):
            w.log(f"BLOCKED  {s}")
            say(f"I won't run '{s}'. It could change or delete files.", "Guard")
            return
    for s in steps:
        s, why = w.sanitize_command(s)
        if s is None:
            w.log(f"REJECTED {why}")
            say(why + ".", "Guard")
            continue
        if why:
            w.log(f"REPAIRED {s} ({why})")
            say(f"(fixed: {why})", "Action", voice=False)
        if w.dlam_on() and w.SAFE.match(s):
            say(f"[DLAM auto] {s}\n" + run_ps(s), "Action")
        else:
            PENDING.append({"id": uuid.uuid4().hex[:8], "cmd": s})
            UIQ.put(("pending", None))
            say(f"Waiting for your approval: {s}", "Action", voice=False)


def _respond(text):
    low = (text or "").lower().strip()
    if not low:
        return
    say(text, "Tyree", voice=False)
    if "autonomous" in low or "phase lock" in low:
        w.DLAM_FILE.write_text("on", encoding="utf-8")
        return say("Phi phase lock on. DLAM is running: safe actions go by themselves, writing and math need nothing from you, and only risky steps wait for one click.")
    if low in ("dlam off", "/dlam off", "stop dlam"):
        if w.DLAM_FILE.exists():
            w.DLAM_FILE.unlink()
        return say("DLAM off. I'll ask before every command.")
    if low in ("dlam", "/dlam", "infinite dlam", "dlam on"):
        w.DLAM_FILE.write_text("on", encoding="utf-8")
        return say("DLAM on. Safe commands run without asking, until you say DLAM off.")
    if re.match(r"^(please\s+)?(open|launch|start|run)\b", low):
        app = re.sub(r"^(please\s+)?(open|launch|start|run)\s+(up\s+)?(the\s+)?|[.!?\s]+$", "", low)
        if app in APPS:
            if w.dlam_on():
                return say(f"Opening {app}.\n" + run_ps(APPS[app]), "Action")
            return handle_command(APPS[app])
    seen = we.handle(text, say, wl.handle)
    if seen:
        return say(seen)
    launched = wl.handle(text)
    if launched:
        return say(launched, "Action")
    try:
        if low.startswith("/calc "):
            return say(f"{text[6:]} = {ww.calc(text[6:])}")
        qm = ww.quick_math(low)
        if qm:
            return say(f"{qm} = {ww.calc(qm)}")
        if ww.WRITE_WORDS.search(low) and ww.WRITE_THINGS.search(low):
            say("Writing it now...", "Action", voice=False)
            return say(ww.write_doc(text, text))
        if low.startswith("/web "):
            return say(ww.answer_from_web(text[5:], text[5:]))
        UIQ.put(("status", "Thinking…"))
        t0 = time.time()
        reply = ww.ask(ww.SEARCH_PROMPT, HISTORY[-8:] + [{"role": "user", "content": text}])
        HISTORY.extend([{"role": "user", "content": text}, {"role": "assistant", "content": json.dumps(reply)}])
        query = str(reply.get("search", "")).strip()
        if query:
            UIQ.put(("status", "Searching…"))
            return say(ww.answer_from_web(text, query))
        topic = str(reply.get("write", "")).strip()
        if topic:
            say("Writing it now...", "Action", voice=False)
            return say(ww.write_doc(text, topic))
        line, expr = str(reply.get("say", "")), str(reply.get("calc", "")).strip()
        if expr:
            line = f"{line} {expr} = {ww.calc(expr)}".strip()
        say(f"{line}  ({time.time() - t0:.1f}s)")
        command = str(reply.get("command", "")).strip()
        if command:
            handle_command(command)
    except Exception as e:
        if "timed out" in str(e).lower() or "timeout" in str(e).lower():
            say("The brain took too long to answer that one. I'm still here — try again and I'll pick it up fresh.", "Guard")
        elif "gemma3:12b" in str(e) or "brain" in str(e).lower():
            say("My brain isn't back yet — I'm bringing it up myself. Try again in a moment.", "Guard")
        else:
            say(f"Something went wrong: {e}", "Guard")
    finally:
        UIQ.put(("status", "Ready"))


def respond(text):
    # Ears and typing both land here. Brain work runs off the UI thread.
    threading.Thread(target=_respond, args=(text,), daemon=True).start()


# ---------- the floating widget (tkinter only — built into Python) ----------
root = None
bubble = None
chat = None
log_text = None
entry = None
status_lbl = None
mic_lbl = None
voice_btn = None
pending_frame = None
pending_lbl = None
_mode = {"chat": False}
_drag = {}


def _corner(w, h):
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    return sw - w - 20, sh - h - 60  # bottom-right, clear of the taskbar


def _place_bubble():
    x, y = _corner(BUBBLE, BUBBLE)
    root.geometry(f"{BUBBLE}x{BUBBLE}+{x}+{y}")


def _place_chat():
    x, y = _corner(CHAT_W, CHAT_H)
    root.geometry(f"{CHAT_W}x{CHAT_H}+{x}+{y}")


def _show_bubble():
    _mode["chat"] = False
    chat.pack_forget()
    bubble.pack(fill="both", expand=True)
    _place_bubble()


def _show_chat():
    _mode["chat"] = True
    bubble.pack_forget()
    chat.pack(fill="both", expand=True)
    _place_chat()
    entry.focus_set()


def _quit():
    _release_lock()
    try:
        root.destroy()
    except Exception:
        pass
    os._exit(0)


def _start_drag(event):
    _drag["x"], _drag["y"] = event.x_root, event.y_root
    _drag["wx"], _drag["wy"] = root.winfo_x(), root.winfo_y()
    _drag["moved"] = False


def _do_drag(event):
    dx, dy = event.x_root - _drag["x"], event.y_root - _drag["y"]
    if abs(dx) + abs(dy) > 4:
        _drag["moved"] = True
    root.geometry(f"+{_drag['wx'] + dx}+{_drag['wy'] + dy}")


def _bubble_release(event):
    if not _drag.get("moved"):
        _show_chat()


def _toggle_voice():
    VOICE["on"] = not VOICE["on"]
    voice_btn.config(text="VOICE ON" if VOICE["on"] else "VOICE OFF",
                     fg=GRN if VOICE["on"] else DIM)
    if not VOICE["on"]:
        UIQ.put(("status", "Voice off — text only"))


def _send_typed(event=None):
    text = entry.get().strip()
    if not text:
        return
    entry.delete(0, "end")
    respond(text)


def _pending_run():
    if not PENDING:
        return
    item = PENDING.pop(0)
    UIQ.put(("pending", None))

    def go():
        say(f"[approved] {item['cmd']}\n" + run_ps(item["cmd"]), "Action")
    threading.Thread(target=go, daemon=True).start()


def _pending_no():
    if not PENDING:
        return
    item = PENDING.pop(0)
    UIQ.put(("pending", None))
    w.log(f"DECLINED {item['cmd']}")
    say(f"Skipped: {item['cmd']}", "Action", voice=False)


def _apply_ui(item):
    kind = item[0]
    if kind == "say":
        _, who, text = item
        tag = {"Willow": "willow", "Tyree": "tyree", "Guard": "guard", "Action": "action"}.get(who, "willow")
        log_text.config(state="normal")
        log_text.insert("end", f"{who}: {text}\n\n", tag)
        log_text.see("end")
        log_text.config(state="disabled")
    elif kind == "status":
        status_lbl.config(text=item[1])
    elif kind == "ears":
        mic_lbl.config(text="● Listening" if item[1] == "listening" else
                       "● Starting…" if item[1] == "starting…" else "● Ears off",
                       fg=GRN if item[1] == "listening" else DIM)
    elif kind == "pending":
        if PENDING:
            pending_lbl.config(text=PENDING[0]["cmd"])
            pending_frame.pack(fill="x", padx=8, pady=(0, 6))
        else:
            pending_frame.pack_forget()


def _pump():
    try:
        while True:
            _apply_ui(UIQ.get_nowait())
    except queue.Empty:
        pass
    if root is not None:
        root.after(120, _pump)


def _build_ui():
    global root, bubble, chat, log_text, entry, status_lbl, mic_lbl, voice_btn
    global pending_frame, pending_lbl
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=BG)
    root.bind("<Escape>", lambda e: _show_bubble() if _mode["chat"] else None)

    # --- the bubble: a gold phi that lives on the desktop ---
    bubble = tk.Canvas(root, width=BUBBLE, height=BUBBLE, bg=BG, highlightthickness=0)
    bubble.create_oval(6, 6, BUBBLE - 6, BUBBLE - 6, outline=GOLD, width=2, fill=PANEL)
    bubble.create_text(BUBBLE // 2, BUBBLE // 2 - 2, text="φ", fill=GOLD2,
                       font=("Consolas", 44, "bold"))
    bubble.bind("<ButtonPress-1>", _start_drag)
    bubble.bind("<B1-Motion>", _do_drag)
    bubble.bind("<ButtonRelease-1>", _bubble_release)

    # --- the chat panel ---
    chat = tk.Frame(root, bg=BG)
    head = tk.Frame(chat, bg=PANEL)
    head.pack(fill="x")
    tk.Label(head, text="φ  WILLOW", fg=GOLD2, bg=PANEL, font=FONT_B).pack(side="left", padx=8, pady=6)
    mic_lbl = tk.Label(head, text="● Starting…", fg=DIM, bg=PANEL, font=("Consolas", 9))
    mic_lbl.pack(side="left", padx=4)
    tk.Button(head, text="×", fg=RED, bg=PANEL, bd=0, font=FONT_B, command=_quit).pack(side="right", padx=4)
    tk.Button(head, text="—", fg=DIM, bg=PANEL, bd=0, font=FONT_B, command=_show_bubble).pack(side="right")
    voice_btn = tk.Button(head, text="VOICE ON", fg=GRN, bg=PANEL, bd=0, font=("Consolas", 9, "bold"),
                          command=_toggle_voice)
    voice_btn.pack(side="right", padx=4)
    for wd in (head,):
        wd.bind("<ButtonPress-1>", _start_drag)
        wd.bind("<B1-Motion>", _do_drag)

    log_frame = tk.Frame(chat, bg=BG)
    log_frame.pack(fill="both", expand=True, padx=8, pady=(6, 0))
    sb = tk.Scrollbar(log_frame, orient="vertical")
    log_text = tk.Text(log_frame, bg=BG, fg=TXT, font=FONT, wrap="word",
                       state="disabled", yscrollcommand=sb.set, bd=0,
                       highlightthickness=0, insertbackground=TXT)
    sb.config(command=log_text.yview)
    sb.pack(side="right", fill="y")
    log_text.pack(side="left", fill="both", expand=True)
    log_text.tag_config("willow", foreground=GOLD2)
    log_text.tag_config("tyree", foreground=CYAN)
    log_text.tag_config("guard", foreground=RED)
    log_text.tag_config("action", foreground=DIM)

    pending_frame = tk.Frame(chat, bg="#2a0c14", highlightbackground=RED, highlightthickness=1)
    pending_lbl = tk.Label(pending_frame, text="", fg=GOLD2, bg="#2a0c14",
                           font=("Consolas", 10), wraplength=340, justify="left")
    pending_lbl.pack(side="left", fill="x", expand=True, padx=6, pady=4)
    tk.Button(pending_frame, text="RUN", bg=GOLD, fg="#120c00", bd=0,
              font=FONT_B, command=_pending_run).pack(side="right", padx=4)
    tk.Button(pending_frame, text="NO", bg="#2a0c14", fg=RED, bd=0,
              font=FONT_B, command=_pending_no).pack(side="right")

    row = tk.Frame(chat, bg=BG)
    row.pack(fill="x", padx=8, pady=6)
    entry = tk.Entry(row, bg="#050a1a", fg=TXT, font=FONT, bd=0,
                     highlightthickness=1, highlightbackground=LINE, insertbackground=TXT)
    entry.pack(side="left", fill="x", expand=True, ipady=8)
    entry.bind("<Return>", _send_typed)
    tk.Button(row, text="SEND", bg=GOLD, fg="#120c00", bd=0, font=FONT_B,
              command=_send_typed).pack(side="right", padx=(6, 0), ipady=6, ipadx=8)

    status_lbl = tk.Label(chat, text="Starting…", fg=DIM, bg=BG, font=("Consolas", 9), anchor="w")
    status_lbl.pack(fill="x", padx=10, pady=(0, 6))
    tk.Label(chat, text="Listening — say Willow. DLAM on, phi first, all local.",
             fg=DIM, bg=BG, font=("Consolas", 9), anchor="w").pack(fill="x", padx=10, pady=(0, 8))

    bubble.pack(fill="both", expand=True)
    _place_bubble()


# ---------- boot: brain server, telemetry, ears ----------
def _ollama_up(port=11434, timeout=2):
    # Thin wrapper over the shared brain check in willow_type, so the
    # widget, the Command Center and Emma all read the same ports.
    return w._ollama_up(port, timeout=timeout)


def _model_present(port=11434, timeout=3):
    # The server answering only proves a server is up - not that it
    # has the brain. Ollama answers 404 for a model that is not in the
    # serving instance's store (wrong model folder), so check the model
    # too, on the port asked for (11434 normally, 11435 fallback).
    return w._model_present(port, timeout=timeout)


def _ensure_ollama():
    """Bring Willow's brain back, the same way Emma does: 11434 first,
    then the 11435 fallback from the verified folder on disk. The
    stuck Ollama on 11434 is never killed and never restarted, and
    nothing is ever downloaded - the model is already on this PC.
    Returns True when a brain lists gemma3:12b. On failure the Guard
    says plainly that the brain is not back yet and that Willow is
    bringing it up herself - never that Tyree should check a folder,
    restart anything, or start Ollama."""
    if w.ensure_ollama():
        return True
    reason = w._LAST_BRAIN_ERROR or "the brain is not back yet"
    UIQ.put(("say", "Guard",
             "My brain isn't back yet - I'm bringing it up myself, no need to check anything. "
             f"({reason})"))
    return False


def _boot():
    try:
        willow_telemetry.install(ww, w)
    except Exception as e:
        UIQ.put(("say", "Guard", f"Telemetry didn't load: {e}"))
    # Her ears are ON from boot. She always listens for "Willow" — the
    # wake word is the only gate. Speech without it is ignored, never
    # transcribed into her chat.
    try:
        we_ears.start(respond, say, w)
        UIQ.put(("ears", "listening"))
    except Exception as e:
        UIQ.put(("ears", "off"))
        UIQ.put(("say", "Guard", f"Mic didn't start ({e}). Type instead — I still talk back."))
    try:
        with urllib.request.urlopen("http://127.0.0.1:1618/api/vitals", timeout=1) as r:
            if r.status == 200:
                UIQ.put(("say", "Guard", "Note: the Command Center site is also running — she'll answer in both places. Close that window for widget-only."))
    except Exception:
        pass
    if _ensure_ollama():
        port = w.resolve_ollama_port()
        UIQ.put(("status", "Brain awake" + (f" (port {port})" if port else "")))
    else:
        UIQ.put(("status", "Brain offline — healing itself"))
    say("I'm here, Tyree. Talk to me or type — I'm listening.")


def main():
    if not _single_instance():
        return
    try:
        _build_ui()
    except Exception:
        _release_lock()
        raise
    UIQ.put(("say", "Willow", "Widget online. Brain: local gemma3:12b. Voice: local Kokoro. All phi, all free."))
    UIQ.put(("status", "Starting…"))
    root.after(120, _pump)
    threading.Thread(target=_boot, daemon=True).start()
    try:
        root.mainloop()
    finally:
        _release_lock()


if __name__ == "__main__":
    main()
