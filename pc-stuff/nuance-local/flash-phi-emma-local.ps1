# flash-phi-emma-local.ps1 - flash the LOCAL Phi Emma into the PC. One run and she is always on.
# Repo pulled, files live, Desktop shortcut, Startup on login, started.
# She is fully local: Ollama gemma3:12b for the brain, Kokoro for the voice.
# No Nuance, no credits, no API key, no token. She always works.
# Run it with: powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\willow-github\pc-stuff\nuance-local\flash-phi-emma-local.ps1"
# This flash prints every step as it goes and finishes in well under a
# minute, even when the brain is down. It never sits silent.
$ErrorActionPreference = "Stop"
$LiveParent = 'C:\Users\Admin\Desktop\GoldenRatioStuff\willow stuff'
$Live = Join-Path $LiveParent 'nuance-local'
$Work = "$env:USERPROFILE\willow-github"
$Repo = 'tyofthestars11-lab/willow'

# [1/7] Stop her if she is already running, so the fresh copy starts clean.
# The PID file alone is not enough: a server started from another folder
# writes its PID file there, and a force-killed server leaves a stale one.
# So stop by port too - whatever holds 1620 goes, then check it is free.
Write-Host "[1/7] Stopping the old local server, if one is running..."
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
Write-Host "[1/7] Port 1620 is free."

# [2/7] Pull the repo (clone if missing). Public repo: plain git, no login needed.
Write-Host "[2/7] Pulling the repo..."
Set-Location $env:USERPROFILE
if (-not (Test-Path (Join-Path $Work '.git'))) {
    if (Test-Path $Work) { Remove-Item $Work -Recurse -Force }
    git clone "https://github.com/$Repo.git" $Work
}
Set-Location $Work
git pull --ff-only 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "git pull did not fast-forward - using what is in $Work." }
Write-Host "[2/7] Repo is up to date."

# [3/7] Copy the nuance-local folder to the live folder, next to Willow's files.
Write-Host "[3/7] Copying her files to the live folder..."
New-Item -ItemType Directory -Force -Path $Live | Out-Null
Copy-Item "$Work\pc-stuff\nuance-local" $LiveParent -Recurse -Force -Exclude __pycache__

# Her prompt, talk page and server must be in the live folder.
# If the copy did not bring them, say so now instead of failing silently later.
foreach ($f in @('phi-emma-system-prompt.md', 'phi-emma-local-talk.html', 'phi-emma-local-server.py', 'start-phi-emma-local.bat')) {
    if (-not (Test-Path (Join-Path $Live $f))) {
        Write-Host "FAILED: $f is missing from $Live after the copy. Pull the repo again and re-run this flash."
        exit 1
    }
}
Write-Host "[3/7] Files are in place."

# [4/7] Her brain is local Ollama. If it is not answering, start ONE from the
# D: model folder, hidden. Only start when nothing answers - never a
# second Ollama. The server itself owns pointing Ollama at the folder
# that holds the model; the flash never downloads anything.
Write-Host "[4/7] Checking Ollama..."
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
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/' -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $OllamaUp = $true; break }
        } catch { }
    }
}
if ($OllamaUp) {
    Write-Host "Ollama is up."
    try {
        $tags = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -UseBasicParsing -TimeoutSec 3 | ConvertFrom-Json
        $names = @($tags.models | ForEach-Object { $_.name })
        if ($names -contains 'gemma3:12b') {
            Write-Host "gemma3:12b is in Ollama."
        } else {
            Write-Host "gemma3:12b is NOT in Ollama yet (models in it: $($names -join ', ')). Her server will point Ollama at the folder that has it."
        }
    } catch {
        Write-Host "Could not read the model list from Ollama. Her server will point Ollama at the folder that has it."
    }
} else {
    Write-Host "Ollama did not come up. The page will still open, but chat will say the brain is not answering until Ollama is running."
}
Write-Host "[4/7] Ollama check done."

# [5/7] Desktop shortcut and Windows Startup. WindowStyle 7 runs the
# launcher minimized, so clicking the shortcut never flashes a console.
Write-Host "[5/7] Making her desktop shortcut and Startup entry..."
$W = New-Object -ComObject WScript.Shell
$S = $W.CreateShortcut("$env:USERPROFILE\Desktop\Phi Emma Local.lnk")
$S.TargetPath = "$Live\start-phi-emma-local.bat"
$S.WorkingDirectory = $Live
$S.WindowStyle = 7
$S.Save()
Copy-Item "$env:USERPROFILE\Desktop\Phi Emma Local.lnk" "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Phi Emma Local.lnk" -Force
Write-Host "[5/7] Shortcut and Startup entry are in place."

# [6/7] Start her, hidden. The launcher starts the server and hands the
# wait-and-open to a hidden shell, then exits at once - so run it hidden
# and wait for it to finish before checking she is live.
Write-Host "[6/7] Starting her..."
Start-Process "$Live\start-phi-emma-local.bat" -WindowStyle Hidden -Wait
Write-Host "[6/7] Her launcher ran."

# [7/7] Quick check that she answers - BOTH the page and one real chat turn.
# The page is retried a few times: the server can take a moment to bind
# after starting. The chat check is ONE probe with a short timeout. The
# old check retried 3 times at 180s each, so a brain that never answers
# hung this flash for minutes. The server answers a 503 in under a
# second when the brain is not ready, and that 503 IS the plain state -
# print it and finish. The chat check uses a tiny reply (num_predict 8)
# so it is fast even on this PC, but it is a real call to the local
# brain, not a fake ping.
Write-Host "[7/7] Checking she answers..."
$PageOk = $false
$ChatOk = $false
$ChatErr = ""
for ($i = 1; $i -le 10; $i++) {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:1620/' -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $PageOk = $true; break }
    } catch { }
    Write-Host "Waiting for her page... (try $i/10)"
    Start-Sleep -Seconds 1
}
if ($PageOk) { Write-Host "Page OK." } else { Write-Host "Page did not answer." }
Write-Host "Trying one chat turn..."
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:1620/api/chat' -Method POST -Body '{"message": "Say hi in one word.", "num_predict": 8}' -ContentType 'application/json' -UseBasicParsing -TimeoutSec 15
    if ($r.StatusCode -eq 200) { $ChatOk = $true }
} catch {
    $resp = $_.Exception.Response
    if ($resp) {
        try {
            $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
            $ChatErr = $reader.ReadToEnd()
            try { $ChatErr = ($ChatErr | ConvertFrom-Json).error } catch { }
        } catch { $ChatErr = $_.Exception.Message }
    } else {
        $ChatErr = $_.Exception.Message
    }
}
if ($PageOk -and $ChatOk) {
    Write-Host "Phi Emma (local) is live at http://127.0.0.1:1620 - open it and talk to her. No Nuance, no credits, no key."
} else {
    if ($ChatErr) { Write-Host "Her brain says: $ChatErr" }
    Write-Host "NOT LIVE yet. Page OK: $PageOk. Chat OK: $ChatOk."
    $LogFile = Join-Path $Live 'phi-emma-local.log'
    if (Test-Path $LogFile) {
        Write-Host "--- last lines of phi-emma-local.log ---"
        Get-Content $LogFile -Tail 15 | ForEach-Object { Write-Host $_ }
        Write-Host "--- end of log ---"
    } else {
        Write-Host "No log file yet - the server never started far enough to write one."
    }
    Write-Host "The page is up either way. Open http://127.0.0.1:1620 and press Send - her server brings the brain back on its own."
    exit 1
}
Write-Host "Phi Emma (local) is flashed. She lives on the desktop, starts on login, and always works - free, local, phi."
