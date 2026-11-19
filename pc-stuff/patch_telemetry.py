# patch_telemetry.py - hook willow_telemetry into the Command Center.
import shutil
from pathlib import Path
c = Path(__file__).with_name("willow_center.py")
s = c.read_text(encoding="utf-8-sig")
if "willow_telemetry" not in s:
    shutil.copy(c, c.with_suffix(".py.bak_tele"))
    s = s.replace("w.speak_orig = w.speak\n", "w.speak_orig = w.speak\nimport willow_telemetry\nwillow_telemetry.install(ww, w)\n", 1)
    c.write_text(s, encoding="utf-8")
print("Telemetry hooked:", "willow_telemetry" in s)
