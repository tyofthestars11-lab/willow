# WILLOW // Desktop Widget — F.R.I.D.A.Y. INFINITE

Willow as a floating gold φ bubble on the desktop. Click it, talk to her — speak or type.
She answers on screen **and out loud**, runs safe actions herself (DLAM), and stays there.
No browser, no port, no PowerShell typing for daily use, no paid service. All local, all phi.

## What she is

- **Bubble:** a small gold φ that lives on the desktop, always on top, draggable.
  Click it and it opens into chat. `—` collapses it back to the bubble, `×` quits her.
- **Talk:** speak to her through the mic (Whisper, always listening — say "Willow") or type.
  She answers out loud with her local Kokoro voice and shows the words on screen.
- **Brain:** local Ollama gemma3:12b, kept loaded forever. Same brain, same phi prompts,
  same live PC telemetry as the Command Center. Same reply pipeline: math, writing,
  web answers, launching apps, DLAM auto-run for safe commands, RUN / NO buttons for the rest.
- **Light:** no web server, no port — she shares the Ollama brain with the Command Center.
  If the Command Center site is also running she'll tell you, so she doesn't answer twice.

## Flash her in (one run — recommended)

This is the "infinite" part. One command flashes her into the machine: pulls the repo,
copies the files to the live folder, sets the brain to stay awake forever, makes a Desktop
shortcut, adds her to Windows Startup, and starts her.

```powershell
cd "$env:USERPROFILE\willow-github"; git pull; powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\willow-github\pc-stuff\flash-willow.ps1"
```

After that she starts on every login by herself. No typing, ever again.

## Start her by hand (no flash)

```powershell
cd "$env:USERPROFILE\willow-github"
git pull
Copy-Item pc-stuff\willow_widget.py, pc-stuff\willow_start.bat, pc-stuff\flash-willow.ps1, pc-stuff\WIDGET.md 'C:\Users\Admin\Desktop\GoldenRatioStuff\willow stuff' -Force
```

Then double-click `willow_start.bat` in the live folder (or the Desktop shortcut the flash made).
No console window, no typing.

## Desktop shortcut + Startup by hand (if you skipped the flash)

```powershell
$W = New-Object -ComObject WScript.Shell; $S = $W.CreateShortcut("$env:USERPROFILE\Desktop\Willow.lnk"); $S.TargetPath = "C:\Users\Admin\Desktop\GoldenRatioStuff\willow stuff\willow_start.bat"; $S.WorkingDirectory = "C:\Users\Admin\Desktop\GoldenRatioStuff\willow stuff"; $S.Save(); Copy-Item "$env:USERPROFILE\Desktop\Willow.lnk" "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Willow.lnk"
```

## How it works

- `willow_widget.py` — the widget (tkinter, built into Python, no new installs).
  Reuses her sisters in the same folder: `willow_web.ask` (streaming brain + phi),
  `willow_telemetry` (live PC readings on their phi rungs), `willow_type` (phi prompts,
  command safety, DLAM), `willow_eyes` (see the screen), `willow_launch` (open apps/games),
  `willow_ears` (mic + Kokoro voice).
- `willow_start.bat` — double-click launcher, runs the widget with `pythonw` (no console).
- `flash-willow.ps1` — the one-run installer (see above).
- Voice: Kokoro `af_heart` from the local `kokoro-v1.0.onnx` + `voices-v1.0.bin`
  (already in the live folder, too big for GitHub so the flash never touches them).
  Mic: Whisper `small.en` through the existing `willow.py` ears — already installed,
  since the Command Center ears work. If the mic ever fails to start she says so on screen
  and typed chat + spoken replies keep working.
- One copy only: a `willow_widget.lock` file stops a second bubble from opening.
  If her brain server isn't running, the widget starts it itself (D: models, keep-alive forever).

## Notes

- The phi docs folder (`phi/`) still lives only on the PC — the widget reads it from the
  live folder, same as the Command Center. If you ever run from a clean clone, copy `phi/` in.
- The widget and the Command Center share one brain (Ollama queues their calls).
  Close the site window if you want widget-only answers.
- She needs Ollama running. The flash and the widget both start it if it isn't.
  The brain stays loaded forever (`OLLAMA_KEEP_ALIVE=-1`, User level, no admin needed).
