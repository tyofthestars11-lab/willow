# willow_telemetry.py - Willow sees the whole PC and Tyree's whole framework, every message.
# Each time she thinks, she gets: live PC telemetry (CPU, RAM, GPU, disks, top processes, uptime)
# with every reading on its phi rung, plus the parts of Tyree's framework (the phi folder:
# his mind file, his GitHub docs, his PhiFramework notes) that match what he just said.
import json, math, re, shutil, subprocess, time, urllib.request
from pathlib import Path

PHI = (1 + 5 ** 0.5) / 2
HERE = Path(__file__).parent
PHI_DIR = HERE / "phi"
CHUNKS = []


def rung(x):
    return math.log(x) / math.log(PHI) if x and x > 0 else float("nan")


def tag(name, x, unit=""):
    return f"{name} {x:g}{unit} (rung {rung(x):.3f})" if x and x > 0 else f"{name} {x}{unit}"


def load_framework():
    CHUNKS.clear()
    if not PHI_DIR.exists():
        return
    for p in sorted(PHI_DIR.rglob("*")):
        if p.suffix.lower() not in (".md", ".txt"):
            continue
        text = p.read_text(encoding="utf-8-sig", errors="ignore")
        for part in re.split(r"\n\s*\n", text):
            part = part.strip()
            while part:
                CHUNKS.append((p.name, part[:987]))
                part = part[987:]


def framework_for(question, budget=8000):
    words = set(re.findall(r"[a-z0-9]{3,}", question.lower())) | {"phi", "rung", "fibonacci", "lucas"}
    scored = []
    for i, (name, text) in enumerate(CHUNKS):
        low = text.lower()
        score = sum(low.count(wd) for wd in words)
        if name.lower().startswith("willow_mind"):
            score += 1000  # his core framework always rides along
        scored.append((score, -i, name, text))
    scored.sort(reverse=True)
    out, used = [], 0
    for score, _, name, text in scored:
        if score <= 0 or used + len(text) > budget:
            continue
        out.append(f"[{name}] {text}")
        used += len(text)
    return "\n".join(out)


def telemetry():
    lines = [time.strftime("Now: %A %Y-%m-%d %H:%M:%S local")]
    try:
        import psutil
        lines.append(tag("CPU load", psutil.cpu_percent(interval=0.3), "%") + f", {psutil.cpu_count()} threads")
        vm = psutil.virtual_memory()
        lines.append(tag("RAM used", round(vm.used / 2**30, 2), " GB") + f" of {vm.total / 2**30:.1f} GB ({vm.percent}%)")
        up = time.time() - psutil.boot_time()
        lines.append(tag("Uptime", round(up / 3600, 2), " h"))
        procs = sorted(psutil.process_iter(["name", "memory_info"]),
                       key=lambda p: p.info["memory_info"].rss if p.info["memory_info"] else 0, reverse=True)[:8]
        lines.append("Top programs by memory: " + ", ".join(
            f"{p.info['name']} {p.info['memory_info'].rss / 2**20:.0f} MB" for p in procs if p.info["memory_info"]))
        net = psutil.net_io_counters()
        lines.append(tag("Network sent", round(net.bytes_sent / 2**20, 1), " MB") + ", " +
                     tag("received", round(net.bytes_recv / 2**20, 1), " MB"))
        try:
            bat = psutil.sensors_battery()
            if bat:
                lines.append(tag("Battery", bat.percent, "%"))
        except Exception:
            pass
    except ImportError:
        lines.append("(psutil not installed: CPU, RAM and programs unavailable)")
    try:
        q = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout.strip()
        n, u, mu, mt, tc, pw = [x.strip() for x in q.splitlines()[0].split(",")]
        lines.append(f"GPU {n}: " + ", ".join([tag("load", float(u), "%"), tag("VRAM", float(mu), " MB") + f" of {mt} MB",
                                                tag("temp", float(tc), " C"), tag("power", float(pw), " W")]))
    except Exception:
        pass
    try:
        ps = json.loads(urllib.request.urlopen("http://localhost:11434/api/ps", timeout=3).read())
        lines.append("Models loaded: " + ", ".join(m.get("name", "?") for m in ps.get("models", [])))
    except Exception:
        pass
    for d in "CDEFG":
        try:
            t, used, free = shutil.disk_usage(f"{d}:\\")
            lines.append(f"Drive {d}: " + tag("free", round(free / 2**30, 1), " GB") + f" of {t / 2**30:.0f} GB")
        except Exception:
            pass
    return "\n".join(lines)


def install(ww, w):
    load_framework()
    base = ww.SEARCH_PROMPT.split("\n\nTYREE'S FRAMEWORK (his own documents):")[0]

    def ask(system, messages):
        question = messages[-1]["content"] if messages else ""
        full = (base if system == ww.SEARCH_PROMPT else system)
        full += ("\n\nTYREE'S FRAMEWORK (the parts that fit this moment):\n" + framework_for(question) +
                 "\n\nLIVE PC TELEMETRY (read just now, each value on its phi rung):\n" + telemetry() +
                 "\n\nYou can see all of this. Use it when he asks about the PC, himself, time, or anything phi.")
        payload = {"model": w.LLM_MODEL, "stream": True, "format": "json", "keep_alive": -1,
                   "messages": [{"role": "system", "content": full}] + messages,
                   "options": {"temperature": 1 - 1 / w.PHI, "num_predict": 377, "num_ctx": 8192}}
        content = ww._stream_chat(payload)  # stream: gemma is slow, one long read times out
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"say": content}

    ww.ask = ask
    print(f"Telemetry on. Framework: {len(CHUNKS)} pieces from {PHI_DIR}")


if __name__ == "__main__":
    load_framework()
    print(telemetry())
    print(f"\n{len(CHUNKS)} framework pieces loaded")
