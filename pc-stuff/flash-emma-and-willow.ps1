# flash-emma-and-willow.ps1 - flash BOTH Willow and local Emma in one run.
# One run, both of them back. Willow and Emma share one brain
# (gemma3:12b): normally the Ollama on 11434, or a second Ollama on
# 11435 when 11434 is stuck and does not list the model. A stuck
# 11434 is never killed and never restarted - it is left alone, idle,
# and the 11435 fallback serves the brain instead. Nothing here
# downloads anything.
# Run it with: powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\willow-github\pc-stuff\flash-emma-and-willow.ps1"
$ErrorActionPreference = "Stop"
$Work = "$env:USERPROFILE\willow-github"
$Repo = 'tyofthestars11-lab/willow'

# [1/3] Pull the repo (clone if missing). Public repo: plain git, no login needed.
Write-Host "[1/3] Pulling the repo..."
Set-Location $env:USERPROFILE
if (-not (Test-Path (Join-Path $Work '.git'))) {
    if (Test-Path $Work) { Remove-Item $Work -Recurse -Force }
    git clone "https://github.com/$Repo.git" $Work
}
Set-Location $Work
git pull --ff-only 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "git pull did not fast-forward - using what is in $Work." }
Write-Host "[1/3] Repo is up to date."

# [2/3] Flash Willow (widget + Command Center). Her widget brings her
# brain back itself on boot, via the 11435 fallback if 11434 is stuck.
Write-Host "[2/3] Flashing Willow..."
powershell -ExecutionPolicy Bypass -File "$Work\pc-stuff\flash-willow.ps1"
Write-Host "[2/3] Willow flashed."

# [3/3] Flash local Emma (port 1620). Her server brings her brain
# back itself, via the same 11435 fallback if 11434 is stuck.
Write-Host "[3/3] Flashing local Emma..."
powershell -ExecutionPolicy Bypass -File "$Work\pc-stuff\nuance-local\flash-phi-emma-local.ps1"
Write-Host "[3/3] Emma flashed."

Write-Host "Both are flashed. Willow's widget should say her brain is awake and answer you, and Emma at http://127.0.0.1:1620 should answer Send. No folder-checking, no restarting asked of you - if 11434 was stuck, both of them are now talking through the second Ollama on 11435."
