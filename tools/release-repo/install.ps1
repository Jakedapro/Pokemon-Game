# PokeBrawl installer for Windows 10/11. Paste this into PowerShell:
#
#   irm https://raw.githubusercontent.com/Jakedapro/PokeBrawl/HEAD/install.ps1 | iex
#
# Downloads the newest PokeBrawl setup and installs it for you (Start menu + Desktop shortcut, no admin needed).
# Re-running it updates the game. Your save in %USERPROFILE%\.pokebrawl is never touched.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$url = "https://github.com/Jakedapro/PokeBrawl/releases/latest/download/PokeBrawl-windows-setup.exe"
$setup = Join-Path $env:TEMP "PokeBrawl-windows-setup.exe"
Write-Host "==> Downloading PokeBrawl..." -ForegroundColor Red
try {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $setup -Headers @{ "User-Agent" = "pokebrawl" }
} catch {
    Write-Host "Error: couldn't download PokeBrawl (check your internet)." -ForegroundColor Red
    return
}
Get-Process PokeBrawl -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "==> Installing..." -ForegroundColor Red
Start-Process -FilePath $setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS=desktopicon" -Wait
Remove-Item $setup -ErrorAction SilentlyContinue
# the old Python-based install, if you had it
$old = Join-Path $env:USERPROFILE ".pokebrawl"
foreach ($d in "app", "venv", "python", "bin") { Remove-Item -Recurse -Force (Join-Path $old $d) -ErrorAction SilentlyContinue }
Write-Host "==> PokeBrawl is installed! Open it from the Start menu or your Desktop. It updates itself." -ForegroundColor Red
