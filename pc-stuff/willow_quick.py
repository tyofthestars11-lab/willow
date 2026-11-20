import json, subprocess, time, urllib.request
# The brain is whichever Ollama lists gemma3:12b - 11434 normally,
# 11435 when the fallback is serving it.
def _brain_url():
    for base in ("http://127.0.0.1:11434", "http://127.0.0.1:11435"):
        try:
            with urllib.request.urlopen(base + "/api/tags", timeout=3) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            for m in data.get("models", []):
                name = m.get("name", "")
                if name == "gemma3:12b" or name.startswith("gemma3:12b:"):
                    return base + "/api/chat"
        except Exception:
            continue
    return "http://localhost:11434/api/chat"
URL = _brain_url()
Q = ["What is 89 plus 144?", "In one sentence, what is the golden ratio?", "Say hello to Tyree in five words.", "Give a one-line quest idea for a glowing beacon.", "Name three things a game hub market needs."]
def ask(p):
    b = json.dumps({"model": "gemma3:12b", "stream": False, "keep_alive": -1, "options": {"num_predict": 144}, "messages": [{"role": "user", "content": p}]}).encode()
    t = time.time()
    d = json.loads(urllib.request.urlopen(urllib.request.Request(URL, data=b, headers={"Content-Type": "application/json"}), timeout=120).read())
    return time.time() - t, d.get("eval_count", 0) / (d.get("eval_duration", 1) / 1e9)
secs, tps = [], []
for i in range(13):
    s, r = ask(Q[i % 5]); secs.append(s); tps.append(r)
    print(f"#{i+1}  {s:5.2f}s  {r:5.1f} tok/s")
vram = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
print(f"\nWILLOW SCORE: avg {sum(tps)/13:.1f} tok/s, best {max(tps):.1f}, slowest reply {max(secs):.2f}s, fastest {min(secs):.2f}s, VRAM {vram}")
