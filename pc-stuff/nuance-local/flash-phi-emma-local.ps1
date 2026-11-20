# flash-phi-emma-local.ps1 - flash the LOCAL Phi Emma into the PC. One run and she is always on.
# Repo pulled, files live, Desktop shortcut, Startup on login, started.
# She is fully local: Ollama gemma3:12b for the brain, Kokoro for the voice.
# No Nuance, no credits, no API key, no token. She always works.
# Run it with: powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\willow-github\pc-stuff\nuance-local\flash-phi-emma-local.ps1"
$ErrorActionPreference = "Stop"
$LiveParent = 'C:\Users\Admin\Desktop\GoldenRatioStuff\willow stuff'
$Live = Join-Path $LiveParent 'nuance-local'
$Work = "$env:USERPROFILE\willow-github"
$Repo = 'tyofthestars11-lab/willow'

# 0. Stop her if she is already running, so the fresh copy starts clean.
# The PID file alone is not enough: a server started from another folder
# writes its PID file there, and a force-killed server leaves a stale one.
# So stop by port too - whatever holds 1620 goes, then check it is free.
$PidFile = Join-Path $Live 'phi-emma-local-server.pid'
if (Test-Path $PidFile) {
    $OldPid = 0
    if ([int]::TryParse((Get-Content $PidFile -TotalCount 1), [ref]$OldPid) -and $OldPid -gt 0) {
        Get-Process -Id $OldPid -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}
$Listener = Get-NetTCPConnection -LocalPort 1620 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Listener) {
    Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped the old local server on port 1620."
}
for ($i = 0; $i -lt 10; $i++) {
    $StillThere = Get-NetTCPConnection -LocalPort 1620 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $StillThere) { break }
    Start-Sleep -Seconds 1
}
if (Get-NetTCPConnection -LocalPort 1620 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "FAILED: port 1620 is still held after stopping the old server. Close the program holding it and run this flash again."
    exit 1
}

# 1. Pull the repo (clone if missing). Public repo: plain git, no login needed.
Set-Location $env:USERPROFILE
if (-not (Test-Path (Join-Path $Work '.git'))) {
    if (Test-Path $Work) { Remove-Item $Work -Recurse -Force }
    git clone "https://github.com/$Repo.git" $Work
}
Set-Location $Work
git pull --ff-only 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "git pull did not fast-forward - using what is in $Work." }

# 2. Copy the nuance-local folder to the live folder, next to Willow's files.
New-Item -ItemType Directory -Force -Path $Live | Out-Null
Copy-Item "$Work\pc-stuff\nuance-local" $LiveParent -Recurse -Force -Exclude __pycache__

# 2b. Her prompt, talk page and server must be in the live folder.
# If the copy did not bring them, say so now instead of failing silently later.
foreach ($f in @('phi-emma-system-prompt.md', 'phi-emma-local-talk.html', 'phi-emma-local-server.py', 'start-phi-emma-local.bat')) {
    if (-not (Test-Path (Join-Path $Live $f))) {
        Write-Host "FAILED: $f is missing from $Live after the copy. Pull the repo again and re-run this flash."
        exit 1
    }
}

# 3. Her brain is local Ollama. If it is not answering, start it from the D: model folder.
$OllamaUp = $false
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/' -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) { $OllamaUp = $true }
} catch { }
if (-not $OllamaUp) {
    Write-Host "Ollama is not answering - starting it from D:\PhiMove\.ollama\models."
    $env:OLLAMA_MODELS = 'D:\PhiMove\.ollama\models'
    $env:OLLAMA_KEEP_ALIVE = '-1'
    Start-Process 'ollama' -ArgumentList 'serve' -WindowStyle Hidden
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/' -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $OllamaUp = $true; break }
        } catch { }
    }
}
if ($OllamaUp) { Write-Host "Ollama is up." } else { Write-Host "Ollama did not come up. The page will still open, but chat will say the brain is not answering until Ollama is running." }

# 4. Desktop shortcut for the launcher.
$W = New-Object -ComObject WScript.Shell
$S = $W.CreateShortcut("$env:USERPROFILE\Desktop\Phi Emma Local.lnk")
$S.TargetPath = "$Live\start-phi-emma-local.bat"
$S.WorkingDirectory = $Live
$S.Save()

# 5. Add her to Windows Startup so she launches on login.
Copy-Item "$env:USERPROFILE\Desktop\Phi Emma Local.lnk" "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Phi Emma Local.lnk" -Force

# 6. Start her.
Start-Process "$Live\start-phi-emma-local.bat"
Start-Sleep -Seconds 3

# 7. Quick check that she answers - BOTH the page and a real chat turn.
# The page is retried: the server can take a moment to bind after starting.
# The chat check uses a tiny reply (num_predict 8) so it is fast even on
# this PC, but it is a real call to the local brain, not a fake ping.
# The chat is retried too: her brain may still be downloading on the first
# try, and the retry gives it time to arrive.
$PageOk = $false
$ChatOk = $false
$ChatErr = ""
for ($i = 0; $i -lt 15; $i++) {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:1620/' -UseBasicParsing -TimeoutSec 5
        if ($r.StatusCode -eq 200) { $PageOk = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
for ($i = 0; $i -lt 3; $i++) {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:1620/api/chat' -Method POST -Body '{"message": "Say hi in one word.", "num_predict": 8}' -ContentType 'application/json' -UseBasicParsing -TimeoutSec 180
        if ($r.StatusCode -eq 200) { $ChatOk = $true; break }
        $ChatErr = "HTTP $($r.StatusCode)"
    } catch {
        $ChatErr = $_.Exception.Message
    }
    if (-not $ChatOk) { Start-Sleep -Seconds 5 }
}
if ($PageOk -and $ChatOk) {
    Write-Host "Phi Emma (local) is live at http://127.0.0.1:1620 - open it and talk to her. No Nuance, no credits, no key."
} else {
    Write-Host "FAILED: Phi Emma (local) did not come up clean. Page OK: $PageOk. Chat OK: $ChatOk. $ChatErr"
    $LogFile = Join-Path $Live 'phi-emma-local.log'
    if (Test-Path $LogFile) {
        Write-Host "--- last lines of phi-emma-local.log ---"
        Get-Content $LogFile -Tail 15 | ForEach-Object { Write-Host $_ }
        Write-Host "--- end of log ---"
    } else {
        Write-Host "No log file yet - the server never started far enough to write one."
    }
    Write-Host "If the chat is not OK, her brain (Ollama gemma3:12b) is not answering - start Ollama and run this flash again."
    exit 1
}
Write-Host "Phi Emma (local) is flashed. She lives on the desktop, starts on login, and always works - free, local, phi."
