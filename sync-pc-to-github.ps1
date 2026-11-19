# sync-pc-to-github.ps1 — Willow PC stuff -> GitHub.
# Run on your PC: right-click this file and "Run with PowerShell",
# or copy-paste it into PowerShell and hit Enter.
# It copies the folders listed in $Items into the willow repo (pc-stuff/)
# and pushes them. The Willow and DLAM lines are commented out until
# their exact folders on the PC are confirmed — uncomment and fix the
# paths when you know them. Nothing called DLAM is renamed or deleted.

# Willow PC stuff -> GitHub. Copy-paste this whole block into PowerShell on your PC and hit Enter.
$Repo = "tyofthestars11-lab/willow"
$Work = "$env:USERPROFILE\willow-github"
$Items = @(
  "C:\Users\Admin\phi_system_optimize.ps1"
  # Your Ollama models live under C:\Users\<you>\.ollama\models — that folder is large.
  # Sync the model names (ollama list) rather than the raw blobs, unless you
  # want the full folder on GitHub. Do not add Ollama model blobs by default.
  # "C:\Users\Admin\Willow"
  # "C:\Users\Admin\DLAM"
)
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements
}
if (-not (gh auth status 2>$null)) { gh auth login --web -h github.com }
if (-not (gh repo view $Repo --json name 2>$null)) {
  gh repo create willow --public --description "Willow - real-time voice AI for the phi lattice"
}
if (-not (Test-Path "$Work\.git")) {
  gh repo clone $Repo $Work
} else {
  git -C $Work pull
}
$Dest = Join-Path $Work "pc-stuff"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
foreach ($Item in $Items) {
  if (Test-Path $Item) {
    Copy-Item $Item $Dest -Recurse -Force
    Write-Host "copied: $Item"
  } else {
    Write-Host "not found, skipped: $Item"
  }
}
git -C $Work add -A
git -C $Work commit -m "PC stuff sync $(Get-Date -Format 'yyyy-MM-dd HH:mm')" --allow-empty
git -C $Work push
Write-Host "Done. Your PC stuff is on https://github.com/$Repo"
