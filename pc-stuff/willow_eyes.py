"""Willow's eyes and hands. Eyes: gemma3:12b looks at a screenshot of your screen.
Hands (experimental): "play <game> for N minutes" - she launches it, looks, and clicks/presses keys herself.
Say "stop playing" or slam the mouse into a screen corner to stop her hands."""
import base64, io, json, re, threading, time, urllib.request

EYES_MODEL = "gemma3:12b"
OLLAMA = "http://localhost:11434/api/chat"
STOP = threading.Event()
KEYS = {"space", "enter", "esc", "tab", "w", "a", "s", "d", "e", "f", "i", "m", "j", "1", "2", "3", "4", "5", "6"}
SEE = re.compile(r"\b(what do you see|what'?s on (my|the) screen|look at (my|the) screen|describe (my|the) screen|use your eyes|can you see)\b", re.I)
ALIAS = {"bg3": "baldurs gate 3", "kcd2": "kingdom come deliverance ii", "cyberpunk": "cyberpunk 2077"}
PLAY = re.compile(r"^(?:please\s+)?play\s+(.+?)\s+for\s+(\d+)\s*(?:min|minute|minutes)\b", re.I)


def shot(width=1024):
    import mss
    from PIL import Image
    with mss.mss() as s:
        mon = s.monitors[1]
        raw = s.grab(mon)
    img = Image.frombytes("RGB", raw.size, raw.rgb)
    img.thumbnail((width, width))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode(), (mon["width"], mon["height"])


def look(prompt, b64, fmt=None):
    payload = {"model": EYES_MODEL, "stream": False, "keep_alive": "5m",
               "messages": [{"role": "user", "content": prompt, "images": [b64]}],
               "options": {"temperature": 0.382, "num_predict": 233}}
    if fmt:
        payload["format"] = fmt
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read())["message"]["content"].strip()


def describe(question):
    b64, _ = shot()
    return look(f"This is a screenshot of Tyree's PC screen. {question} Answer in two or three short sentences.", b64)


def play(game, minutes, say, launcher):
    import pyautogui
    pyautogui.FAILSAFE = True
    STOP.clear()
    game = ALIAS.get(game.strip(), game)
    opened = launcher(f"open {game}")
    say(opened or f"I couldn't find {game} to open.", "Action")
    if not opened:
        return
    say("Giving it 60 seconds to load, then my hands take over.", "Action")
    time.sleep(60)
    end, goal, step = time.time() + minutes * 60, f"You are playing {game} for Tyree.", 0
    while time.time() < end and not STOP.is_set():
        step += 1
        try:
            b64, (W, H) = shot()
            raw = look(goal + " Look at the screen and choose ONE next action. Reply only JSON: "
                       '{"see": "what is on screen, a few words", "action": "click" or "key", '
                       '"x": 0-1000, "y": 0-1000, "key": "one of space enter esc tab w a s d e f i m j 1-6"}. '
                       "x and y are the click spot as a fraction of the screen times 1000.", b64, "json")
            a = json.loads(raw)
            if a.get("action") == "click":
                x = int(max(0, min(1000, float(a.get("x", 500)))) * W / 1000)
                y = int(max(0, min(1000, float(a.get("y", 500)))) * H / 1000)
                pyautogui.click(x, y)
                did = f"click {x},{y}"
            elif str(a.get("key", "")).lower() in KEYS:
                pyautogui.press(str(a["key"]).lower())
                did = f"press {a['key']}"
            else:
                did = "wait"
            say(f"[play {step}] I see: {a.get('see', '?')} -> {did}", "Action")
        except pyautogui.FailSafeException:
            say("Mouse in the corner. Hands off.", "Guard")
            break
        except Exception as e:
            say(f"[play {step}] my eyes slipped: {e}", "Guard")
            time.sleep(2)
        time.sleep(1.5)
    say(f"Done playing {game}. {step} moves.", "Action")


def handle(text, say, launcher):
    low = text.lower().strip()
    if "stop playing" in low:
        STOP.set()
        return "Stopping. Hands off."
    m = PLAY.match(low)
    if m:
        threading.Thread(target=play, args=(m.group(1), int(m.group(2)), say, launcher), daemon=True).start()
        return f"Playing {m.group(1)} for {m.group(2)} minute(s). Say stop playing anytime."
    if SEE.search(low):
        try:
            return describe(text)
        except Exception as e:
            return f"My eyes didn't open: {e}"
    return None
