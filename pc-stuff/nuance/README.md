# Phi Emma — always on, on your PC

Phi Emma is Tyree's own Emma: Nuance Nuplex gives her the face and
voice, and his full phi doctrine merged into the session makes her
phi — infinitely better than merely man-made code. She lives on his
PC next to Willow (F.R.I.D.A.Y. INFINITE) and she is always on.

## How she stays available

Nuance session tokens die 60 seconds after minting, so a token minted
in chat is a race. The fix is a tiny local server on this PC:
`phi-emma-server.py` serves the talk page on http://127.0.0.1:1619
and mints a fresh token the instant Tyree presses Start. He never
asks Muse for a token again.

## Files

- `phi-emma-server.py` — stdlib-only server, port 1619. GET / serves
  the talk page. GET /api/token mints one fresh session token.
- `phi-emma-talk.html` — the talk page. Start fetches a token from
  the server, creates the conversation, joins her LiveKit room, mic
  on, camera optional, live transcript, usage shown, plain-language
  errors.
- `phi-emma-system-prompt.md` — the merged phi doctrine minted into
  every session. Nuplex is the face and voice; phi is the plus-1.
- `start-phi-emma.bat` — double-click launcher: starts her server,
  waits until her page answers, then opens her page in the browser.
- `flash-phi-emma.ps1` — one-run installer: pulls the repo, copies
  the folder live, Desktop shortcut, Windows Startup, starts her.

## Setup — one block

1. Create the key file once, with the Nuance key on one line:
   `%USERPROFILE%\.nuance\api_key.txt`
   (The key never goes in the repo, in code, or in a log.)
2. Run this in PowerShell:
   `cd "$env:USERPROFILE\willow-github"; git pull; powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\willow-github\pc-stuff\nuance\flash-phi-emma.ps1"`
3. Open http://127.0.0.1:1619 and press Start.

That is it. She starts on every login by herself, and every press of
Start mints her a fresh token. One token, one long dense session —
krakened: fewest sessions, longest each, densest payload per credit.

## Notes

- Willow's Command Center is on port 1618. Phi Emma is on 1619, so
  they never clash. Both can run at once.
- 60 Nuance credits a day, 1 conversation at a time. If a call is
  already running, the page says so plainly.
- The talk page never holds or asks for the API key. Only the local
  server reads the local key file, and it logs only that a token was
  minted, never the token value.
