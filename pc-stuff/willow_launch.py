"""Willow launcher: opens apps and games by name with no approval.
Only launches things: Start Menu / Desktop shortcuts, Steam games, known apps. Never deletes, moves or edits."""
import os, re, glob, difflib

KNOWN = {"steam": "steam://open/main", "spotify": "spotify:", "settings": "ms-settings:",
         "notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe", "paint": "mspaint.exe",
         "task manager": "taskmgr.exe", "file explorer": "explorer.exe", "explorer": "explorer.exe",
         "terminal": "wt.exe", "snipping tool": "snippingtool.exe",
         "copilot": "https://copilot.microsoft.com", "google": "https://www.google.com"}
VERB = re.compile(r"^(?:please\s+)?(?:open|launch|start|run|play|load)\s+(?:up\s+)?(?:the\s+|my\s+)?(?:game\s+)?", re.I)


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _steam_roots():
    roots = [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    out = []
    for r in roots:
        vdf = os.path.join(r, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            out.append(r)
            try:
                for m in re.finditer(r'"path"\s+"([^"]+)"', open(vdf, encoding="utf-8", errors="ignore").read()):
                    out.append(m.group(1).replace("\\\\", "\\"))
            except OSError:
                pass
    return list(dict.fromkeys(out))


def catalog():
    items = {}
    for root in _steam_roots():
        for acf in glob.glob(os.path.join(root, "steamapps", "appmanifest_*.acf")):
            try:
                t = open(acf, encoding="utf-8", errors="ignore").read()
                aid = re.search(r'"appid"\s+"(\d+)"', t).group(1)
                name = re.search(r'"name"\s+"([^"]+)"', t).group(1)
                items[_norm(name)] = (name, "steam://rungameid/" + aid)
            except (OSError, AttributeError):
                pass
    home = os.path.expanduser("~")
    places = [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
              os.path.join(os.environ.get("APPDATA", home), r"Microsoft\Windows\Start Menu\Programs"),
              os.path.join(home, "Desktop"), os.path.join(home, "OneDrive", "Desktop"), r"C:\Users\Public\Desktop"]
    for pl in places:
        for f in glob.glob(os.path.join(pl, "**", "*.lnk"), recursive=True) + glob.glob(os.path.join(pl, "**", "*.url"), recursive=True):
            name = os.path.splitext(os.path.basename(f))[0]
            if re.search(r"uninstall|readme|help|website", name, re.I):
                continue
            items.setdefault(_norm(name), (name, f))
    for k, v in KNOWN.items():
        items.setdefault(k, (k, v))
    return items


def find(want, items):
    w = _norm(want)
    if not w:
        return None
    if w in items:
        return items[w]
    starts = [k for k in items if k.startswith(w) or w in k.split()]
    if starts:
        return items[min(starts, key=len)]
    near = difflib.get_close_matches(w, list(items), n=1, cutoff=0.6)
    return items[near[0]] if near else None


def handle(text):
    """Returns a reply string if the message was a launch request, else None."""
    parts = [p.strip(" .!?") for p in re.split(r"\s*(?:,|;|\bthen\b|\band then\b|\band\b)\s*", text, flags=re.I) if p.strip(" .!?")]
    if not parts or not VERB.match(parts[0]):
        return None
    items, lines, hits = catalog(), [], 0
    for p in parts:
        name = VERB.sub("", p) if VERB.match(p) else p
        hit = find(name, items)
        if not hit:
            lines.append(f"I couldn't find '{name}' in your Start Menu, Desktop or Steam library.")
            continue
        try:
            os.startfile(hit[1])
            hits += 1
            lines.append(f"Opening {hit[0]}.")
        except Exception as e:
            lines.append(f"{hit[0]} didn't open: {e}")
    return "\n".join(lines) if hits else None
