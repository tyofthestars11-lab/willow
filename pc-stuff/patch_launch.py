import shutil
p = "willow_center.py"
shutil.copy(p, p + ".bak_launch")
t = open(p, encoding="utf-8-sig").read()
if "import willow_launch" not in t:
    t = t.replace("import willow_web as ww", "import willow_web as ww\nimport willow_launch as wl", 1)
    anchor = '    try:\n        if low.startswith("/calc "):'
    t = t.replace(anchor, '    launched = wl.handle(text)\n    if launched:\n        return say(launched, "Action")\n' + anchor, 1)
    open(p, "w", encoding="utf-8").write(t)
print("Launcher wired in. Backup: willow_center.py.bak_launch" if "wl.handle(text)" in t else "Anchor not found: send Hark a photo")
