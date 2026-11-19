import re, shutil
p = "willow_center.py"
shutil.copy(p, p + ".bak_open")
t = open(p, encoding="utf-8-sig").read()
if "APPS = {" not in t:
    apps = '''APPS = {
    "steam": "Start-Process 'steam://open/main'", "notepad": "Start-Process notepad",
    "calculator": "Start-Process calc", "calc": "Start-Process calc",
    "task manager": "Start-Process taskmgr", "file explorer": "Start-Process explorer",
    "explorer": "Start-Process explorer", "paint": "Start-Process mspaint",
    "edge": "Start-Process msedge", "chrome": "Start-Process chrome", "firefox": "Start-Process firefox",
    "spotify": "Start-Process 'spotify:'", "vs code": "Start-Process code", "terminal": "Start-Process wt",
    "settings": "Start-Process 'ms-settings:'", "snipping tool": "Start-Process snippingtool",
}


def respond(text):'''
    t = t.replace("def respond(text):", apps, 1)
    anchor = '    try:\n        if low.startswith("/calc "):'
    router = '''    if re.match(r"^(please\\s+)?(open|launch|start|run)\\b", low):
        app = re.sub(r"^(please\\s+)?(open|launch|start|run)\\s+(up\\s+)?(the\\s+)?|[.!?\\s]+$", "", low)
        if app in APPS:
            if w.dlam_on():
                return say(f"Opening {app}.\\n" + run_ps(APPS[app]), "Action")
            return handle_command(APPS[app])
'''
    t = t.replace(anchor, router + anchor, 1)
    if not re.search(r"^import re\b|^import .*\bre\b", t, re.M):
        t = "import re\n" + t
    open(p, "w", encoding="utf-8").write(t)
print("Willow open-app fix applied. Backup: willow_center.py.bak_open" if "if app in APPS" in t else "Anchor not found: send Hark a photo")
