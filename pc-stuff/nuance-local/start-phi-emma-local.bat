@echo off
cd /d "%~dp0"
start "" pythonw phi-emma-local-server.py
start "" powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -Command "$u='http://127.0.0.1:1620/'; $deadline=(Get-Date).AddSeconds(30); while ((Get-Date) -lt $deadline) { try { $r=Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { break } } catch { }; Start-Sleep -Seconds 2 }; Start-Process $u"
exit
