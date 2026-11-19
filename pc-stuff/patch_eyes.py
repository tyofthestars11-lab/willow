import shutil
p = "willow_center.py"
shutil.copy(p, p + ".bak_eyes")
t = open(p, encoding="utf-8-sig").read()
if "import willow_eyes" not in t:
    t = t.replace("w = ww.w\n", 'w = ww.w\nw.LLM_MODEL = "gemma3:12b"  # bigger brain\nimport willow_eyes as we\n', 1)
    t = t.replace("    launched = wl.handle(text)\n",
                  "    seen = we.handle(text, say, wl.handle)\n    if seen:\n        return say(seen)\n    launched = wl.handle(text)\n", 1)
    open(p, "w", encoding="utf-8").write(t)
ok = "we.handle(text" in t and "gemma3:12b" in t
print("Eyes, hands and 8B brain wired in. Backup: willow_center.py.bak_eyes" if ok else "Anchor not found: send Hark a photo")
