#!/usr/bin/env python3
r"""Phi Emma local server - she mints her own token, always on.

Serves the Phi Emma talk page on 127.0.0.1:1619 and mints a fresh
Nuance session token the instant Tyree presses Start. No more asking
Muse for a token, no 60-second race in chat.

The Nuance API key comes ONLY from a local key file on this PC:
    %USERPROFILE%\.nuance\api_key.txt   (one line, your Nuance key)
The key is never in this repo, never in this code, never in a log.
If the file is missing, /api/token says so in plain words.

Stdlib only. No new installs. Same shape as willow_center.py.
Willow's Command Center is on 1618; this one is on 1619 so they
never clash.

Run it with:  python phi-emma-server.py
Or double-click start-phi-emma.bat (pythonw, no console).
"""

import atexit
import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 1619
NUANCE_API = "https://api.nuancelabs.ai"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_FILE = os.path.join(BASE_DIR, "phi-emma-system-prompt.md")
TALK_FILE = os.path.join(BASE_DIR, "phi-emma-talk.html")
PID_FILE = os.path.join(BASE_DIR, "phi-emma-server.pid")
PERSONA_ID = "sonia"
END_USER_ID = "tyree"


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def key_file_path():
    if os.name == "nt":
        home = os.environ.get("USERPROFILE", "")
        return os.path.join(home, ".nuance", "api_key.txt")
    return os.path.join(os.path.expanduser("~"), ".nuance", "api_key.txt")


def read_api_key():
    """Read the key fresh each time so Tyree can drop it in without a restart."""
    try:
        with open(key_file_path(), "r", encoding="utf-8") as f:
            key = f.read().strip()
    except OSError:
        return None
    return key or None


def read_prompt():
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def mint_token():
    """Mint one fresh Nuance session token. Returns (token, error_dict)."""
    key = read_api_key()
    if not key:
        return None, {
            "error": "no_api_key",
            "message": "No API key file yet. Create %USERPROFILE%\\.nuance\\api_key.txt "
                       "with your Nuance key on one line, then press Start again.",
        }
    prompt = read_prompt()
    if not prompt:
        return None, {
            "error": "no_prompt",
            "message": "phi-emma-system-prompt.md is missing next to the server. "
                       "Pull the repo again and run the flash script.",
        }
    body = {
        "interface": "nuance_live",
        "personality": {
            "system_prompt": prompt,
            "persona_id": PERSONA_ID,
        },
        "expressiveness": 1,
        "end_user_id": END_USER_ID,
    }
    req = urllib.request.Request(
        NUANCE_API + "/session-tokens",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8"))
        except Exception:
            detail = {}
        code = detail.get("code") or detail.get("error") or ("http_%d" % e.code)
        return None, {"error": code, "status": e.code, "detail": detail}
    except Exception as e:
        return None, {"error": "mint_failed", "message": str(e)}
    token = data.get("token")
    if not token:
        return None, {"error": "mint_failed", "message": "Nuance answered without a token."}
    log("token minted")
    return token, None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # One clean line per request, no headers or bodies in the log.
        log("%s %s" % (self.command, self.path.split("?")[0]))

    def _send_json(self, status, obj):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                payload = f.read()
        except OSError:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(("Missing file: " + os.path.basename(path)).encode("utf-8"))
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send_file(TALK_FILE, "text/html; charset=utf-8")
        elif path == "/api/token":
            token, err = mint_token()
            if err:
                status = 400
                if err.get("error") == "no_api_key":
                    status = 400
                elif err.get("status"):
                    status = err["status"]
                self._send_json(status, err)
            else:
                self._send_json(200, {"token": token})
        elif path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._send_json(404, {"error": "not_found"})


def main():
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    atexit.register(lambda: os.path.exists(PID_FILE) and os.remove(PID_FILE))
    prompt = read_prompt()
    if prompt:
        log("phi prompt loaded (%d chars)" % len(prompt))
    else:
        log("WARNING: phi-emma-system-prompt.md not found next to the server")
    if not read_api_key():
        log("No API key file yet: %s" % key_file_path())
        log("Create that file with your Nuance key on one line, then press Start.")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    log("Phi Emma live at http://%s:%d - press Start on the page, she mints her own token." % (HOST, PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    log("Phi Emma stopped.")


if __name__ == "__main__":
    main()
