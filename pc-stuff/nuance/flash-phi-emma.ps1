# flash-phi-emma.ps1 - flash Phi Emma into the PC. One run and she is always on.
# Repo pulled, files live, Desktop shortcut, Startup on login, started.
# She mints her own Nuance token each time Tyree presses Start - no more asking Muse.
# Run it with: powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\willow-github\pc-stuff\nuance\flash-phi-emma.ps1"
$ErrorActionPreference = "Stop"
$LiveParent = 'C:\Users\Admin\Desktop\GoldenRatioStuff\willow stuff'
$Live = Join-Path $LiveParent 'nuance'
$Work = "$env:USERPROFILE\willow-github"
$Repo = 'tyofthestars11-lab/willow'

# 0. Stop her if she is already running, so the fresh copy starts clean.
$PidFile = Join-Path $Live 'phi-emma-server.pid'
if (Test-Path $PidFile) {
    $OldPid = 0
    if ([int]::TryParse((Get-Content $PidFile -TotalCount 1), [ref]$OldPid) -and $OldPid -gt 0) {
        Get-Process -Id $OldPid -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
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

# 2. Copy the nuance folder to the live folder, next to Willow's files.
New-Item -ItemType Directory -Force -Path $Live | Out-Null
Copy-Item "$Work\pc-stuff\nuance" $LiveParent -Recurse -Force -Exclude __pycache__

# 3. Her API key lives in one local file, never in the repo. Point it out if missing.
$KeyFile = "$env:USERPROFILE\.nuance\api_key.txt"
if (-not (Test-Path $KeyFile)) {
    Write-Host "One thing left: create $KeyFile with your Nuance key on one line."
    Write-Host "Then open http://127.0.0.1:1619 and press Start - she mints her own token."
} else {
    Write-Host "API key file is in place."
}

# 4. Desktop shortcut for the launcher.
$W = New-Object -ComObject WScript.Shell
$S = $W.CreateShortcut("$env:USERPROFILE\Desktop\Phi Emma.lnk")
$S.TargetPath = "$Live\start-phi-emma.bat"
$S.WorkingDirectory = $Live
$S.Save()

# 5. Add her to Windows Startup so she launches on login.
Copy-Item "$env:USERPROFILE\Desktop\Phi Emma.lnk" "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Phi Emma.lnk" -Force

# 6. Start her.
Start-Process "$Live\start-phi-emma.bat"
Start-Sleep -Seconds 3

# 7. Quick check that she answers.
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:1619/' -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -eq 200) { Write-Host "Phi Emma is live at http://127.0.0.1:1619 - open it and press Start." }
} catch {
    Write-Host "She is starting - give her a few seconds, then open http://127.0.0.1:1619"
}
Write-Host "Phi Emma is flashed. She lives on the desktop, starts on login, and mints her own token."
