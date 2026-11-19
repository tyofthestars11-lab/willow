# patch_phi.py - Willow reads Tyree's whole phi framework folder and thinks phi first.
import re, shutil
from pathlib import Path
here = Path(__file__).parent
t = here / "willow_type.py"
s = t.read_text(encoding="utf-8-sig")
shutil.copy(t, here / "willow_type.py.bak_phi")
LOADER = '''PHI_DIR = Path(__file__).with_name("phi")
PHI_TEXT = ""
for _p in sorted(PHI_DIR.glob("*")) if PHI_DIR.exists() else []:
    if _p.suffix.lower() in (".md", ".txt"):
        PHI_TEXT += f"\\n\\n=== {_p.name} ===\\n" + _p.read_text(encoding="utf-8-sig", errors="ignore")
SYSTEM_PROMPT += (
    "\\n\\nPHI FIRST. Tyree's phi framework is how you think. For any number, size, time, count or plan: "
    "find its phi rung first (rung = ln(x)/ln(phi)), use Fibonacci to guide and Lucas to stabilize, "
    "then carry it out with ordinary Cartesian steps (phi^2 = phi + 1: phi is the intent, +1 is the proof). "
    "Say the rung and the result together. Phi shapes your thinking and your answers; use real paths that exist on this PC."
    "\\n\\nTYREE'S FRAMEWORK (his own documents):" + PHI_TEXT[:24000]
)

'''
if "PHI_DIR" not in s:
    s = s.replace("BLOCKED = re.compile(", LOADER + "BLOCKED = re.compile(", 1)
s = re.sub(r'"options": \{"temperature": 1 - 1 / PHI\}', '"options": {"temperature": 1 - 1 / PHI, "num_ctx": 8192}', s)
t.write_text(s, encoding="utf-8")
print("Willow now reads the phi folder:", "PHI_DIR" in s, "| big memory:", "num_ctx" in s)
