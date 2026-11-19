# willow_type.py - type to Willow. She answers on screen and out loud.
# DLAM on: safe commands run with no y/n. Anything else asks. Blocked never runs.
import json, math, re, subprocess, urllib.request
from datetime import datetime
from pathlib import Path

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

PHI = (1 + math.sqrt(5)) / 2
OLLAMA_URL = "http://localhost:11434/api/chat"
LLM_MODEL = "gemma3:12b"
VOICE_ON = True
LOG_FILE = Path(__file__).with_name("willow_log.txt")
DLAM_FILE = Path(__file__).with_name("willow_dlam.txt")  # exists = DLAM on, stays on after restart

SYSTEM_PROMPT = (
    "You are Willow, Tyree's assistant on his Windows 11 PC. "
    "Reply ONLY with JSON: {\"say\": \"...\", \"command\": \"...\"}. "
    "\"say\" is your answer to him. "
    "\"command\" is ONE PowerShell command that does what he asked, or \"\" if no command is needed. "
    "Open apps with Start-Process (notepad, calc, explorer, a URL). "
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
    r"code|wt|taskmgr|snippingtool)(?:\.exe)?(?P=q)|(?P<q2>['\"]?)(?:https?://[^\s'\";|&`]+|ms-settings:[^\s'\";|&`]*)(?P=q2))"
    r"|get-(?:date|process|computerinfo|volume|childitem|location|netipaddress|service)\b[^;|&`]*)\s*$",
    re.IGNORECASE,
)


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
    payload = {"model": LLM_MODEL, "messages": messages, "stream": False,
               "format": "json", "options": {"temperature": 1 - 1 / PHI, "num_ctx": 8192}}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = json.loads(resp.read())["message"]["content"]
    except Exception as e:
        return {"say": f"I can't reach Ollama. Is it running? ({e})", "command": ""}
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

