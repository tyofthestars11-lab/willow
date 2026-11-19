import shutil
p = "willow_center.py"
shutil.copy(p, p + ".bak_ears")
t = open(p, encoding="utf-8-sig").read()
anchor = '    say("Command Center online. I\'m here, Tyree.")'
if "willow_ears" not in t:
    t = t.replace(anchor, '    import willow_ears\n    willow_ears.start(respond, say, w)\n' + anchor, 1)
    open(p, "w", encoding="utf-8").write(t)
print("Ears wired in. Backup: willow_center.py.bak_ears" if "willow_ears.start" in t else "Anchor not found: send Hark a photo")
