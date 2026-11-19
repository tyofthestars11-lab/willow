# flash-willow.ps1 - flash Willow into the PC. One run and she is part of the machine.
# Repo pulled, files live, brain kept awake forever, Desktop shortcut, Startup on login, started.
# Run it with: powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\willow-github\pc-stuff\flash-willow.ps1"
$ErrorActionPreference = "Stop"
$Live = 'C:\Users\Admin\Desktop\GoldenRatioStuff\willow stuff'
$Work = "$env:USERPROFILE\willow-github"
$Repo = 'tyofthestars11-lab/willow'

# 0. Stop her if she is already running, so the fresh copy starts clean.
$Lock = Join-Path $Live 'willow_widget.lock'
if (Test-Path $Lock) {
    $OldPid = 0
    if ([int]::TryParse((Get-Content $Lock -TotalCount 1), [ref]$OldPid) -and $OldPid -gt 0) {
        Get-Process -Id $OldPid -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    Remove-Item $Lock -Force -ErrorAction SilentlyContinue
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

# 2. Copy the willow stuff files to the live folder.
#    Runtime state (log, DLAM switch) is NOT copied. kokoro-v1.0.onnx is too big for
#    GitHub so it is not in the repo - the copy leaves your local one alone.
New-Item -ItemType Directory -Force -Path $Live | Out-Null
Copy-Item "$Work\pc-stuff\*" $Live -Recurse -Force -Exclude __pycache__, willow_log.txt, willow_dlam.txt

# 3. Permanent env vars (User level - no admin needed, survives reboots).
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', 'D:\PhiMove\.ollama\models', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '-1', 'User')

# 4. Make sure her brain server is up (starts the D: server if it is not).
try {
    $env:OLLAMA_MODELS = 'D:\PhiMove\.ollama\models'
    $env:OLLAMA_KEEP_ALIVE = '-1'
    ollama list 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "ollama not answering" }
} catch {
    Write-Host "Ollama was not answering - starting her brain server."
    Start-Process ollama -ArgumentList 'serve' -WindowStyle Minimized -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
}

# 5. Desktop shortcut for the widget launcher.
$W = New-Object -ComObject WScript.Shell
$S = $W.CreateShortcut("$env:USERPROFILE\Desktop\Willow.lnk")
$S.TargetPath = "$Live\willow_start.bat"
$S.WorkingDirectory = $Live
$S.Save()

# 6. Add her to Windows Startup so she launches on login.
Copy-Item "$env:USERPROFILE\Desktop\Willow.lnk" "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Willow.lnk" -Force

# 7. Start her.
Start-Process "$Live\willow_start.bat"
Write-Host "Willow is flashed. She lives on the desktop, starts on login, and her brain stays awake."
