# PokeBrawl one-command installer for Windows 10/11. Paste this into PowerShell:
#
#   irm https://raw.githubusercontent.com/Jakedapro/Pokemon-Game/HEAD/install.ps1 | iex
#
# Installs into %USERPROFILE%\.pokebrawl with its own private Python (nothing else on your PC is touched), adds a
# `pokebrawl` command and PokeBrawl shortcuts on the Desktop and in the Start menu. Re-running it updates the game.
#
# Offline copy (e.g. a PokeBrawl zip from a friend): unzip it and double-click "Install on Windows.bat"
# - the game is installed from that folder instead of being downloaded.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is very slow with its progress bar on
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$OwnerRepo = if ($env:POKEBRAWL_REPO) { $env:POKEBRAWL_REPO } else { "Jakedapro/Pokemon-Game" }
$Branch = if ($env:POKEBRAWL_BRANCH) { $env:POKEBRAWL_BRANCH } else { "HEAD" }
$Root = if ($env:POKEBRAWL_HOME) { $env:POKEBRAWL_HOME } else { Join-Path $env:USERPROFILE ".pokebrawl" }
$App = Join-Path $Root "app"
$PyDir = Join-Path $Root "python"
$Py = Join-Path $PyDir "python.exe"
$Venv = Join-Path $Root "venv"
$VPy = Join-Path $Venv "Scripts\python.exe"
$VPyW = Join-Path $Venv "Scripts\pythonw.exe"
$Bin = Join-Path $Root "bin"
# run from an unzipped copy of the game? then install that copy instead of downloading it
$Local = $env:POKEBRAWL_LOCAL
if (-not $Local -and $PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "pokebrawl\__main__.py"))) { $Local = $PSScriptRoot }
if ($Local -and (Test-Path $App) -and ((Resolve-Path $Local).Path -eq (Resolve-Path $App).Path)) { $Local = $null }

function Say($m) { Write-Host "==> " -ForegroundColor Red -NoNewline; Write-Host $m -ForegroundColor White }
function Warn($m) { Write-Host "!! $m" -ForegroundColor Yellow }
function Die($m) { Write-Host "Error: $m" -ForegroundColor Red; throw $m }
function Get-Url($url, $out) {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $out -Headers @{ "User-Agent" = "pokebrawl" } -ErrorAction Stop
}
function Quiet([scriptblock]$run) {   # run a program ignoring what it prints (PowerShell 5 treats stderr as errors)
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $run *> $null } catch { } finally { $ErrorActionPreference = $prev }
}

New-Item -ItemType Directory -Force -Path $Root, $Bin | Out-Null
$Tmp = Join-Path $Root "download"
Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

# --- 1. a private Python (avoids the Microsoft Store "python" stub and version mix-ups) -------------------------
if (-not (Test-Path $Py)) {
    Say "Downloading a private copy of Python for PokeBrawl (one time, ~30 MB)..."
    $url = $env:POKEBRAWL_PYTHON_URL
    if (-not $url) {
        try {
            $rel = Invoke-RestMethod -UseBasicParsing -ErrorAction Stop "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
            $url = ($rel.assets | Where-Object { $_.name -match '^cpython-3\.12\.\d+\+\d+-x86_64-pc-windows-msvc-install_only\.tar\.gz$' } |
                    Select-Object -First 1).browser_download_url
        } catch { }
    }
    if (-not $url) {
        $url = "https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.12.7+20241016-x86_64-pc-windows-msvc-install_only.tar.gz"
    }
    $tgz = Join-Path $Tmp "python.tar.gz"
    try { Get-Url $url $tgz } catch { Die "Couldn't download Python ($url). Check your internet." }
    Remove-Item -Recurse -Force $PyDir -ErrorAction SilentlyContinue
    tar -xzf $tgz -C $Root
    if (-not (Test-Path $Py)) { Die "Python download looks broken ($url)" }
}
Say "Using $(& $Py --version)"

# --- 2. get the game ----------------------------------------------------------------------------------------------
$old = "none"
if (Test-Path (Join-Path $App "VERSION")) { $old = ((Get-Content (Join-Path $App "VERSION") -Raw) -split "\s+")[0] -replace '^(.{7}).*', '$1' }
if (Test-Path $App) { Say "Updating PokeBrawl..." } else { Say "Downloading PokeBrawl..." }
$x = Join-Path $Tmp "game"
if ($Local) {
    Say "Using the copy in $Local"
    New-Item -ItemType Directory -Force -Path $x | Out-Null
    Copy-Item -Recurse -Force $Local (Join-Path $x "PokeBrawl")
    Remove-Item -Recurse -Force (Join-Path $x "PokeBrawl\.git") -ErrorAction SilentlyContinue
} else {
    $zip = Join-Path $Tmp "game.zip"
    try { Get-Url "https://github.com/$OwnerRepo/archive/$Branch.zip" $zip } catch { Die "Couldn't download the game (check your internet, or install from a PokeBrawl zip)." }
    Expand-Archive -Path $zip -DestinationPath $x -Force
}
$top = Get-ChildItem $x -Directory | Select-Object -First 1
if (-not $top -or -not (Test-Path (Join-Path $top.FullName "pokebrawl\__main__.py"))) { Die "The game download looks wrong." }
# keep showcase files you made yourself
if (Test-Path (Join-Path $App "showcases")) {
    Get-ChildItem (Join-Path $App "showcases") -Filter *.json | ForEach-Object {
        $dest = Join-Path $top.FullName "showcases\$($_.Name)"
        if (-not (Test-Path $dest)) { Copy-Item $_.FullName $dest }
    }
}
Remove-Item -Recurse -Force "$App.new", "$App.old", "$App.download" -ErrorAction SilentlyContinue   # in-game updater leftovers
Remove-Item -Recurse -Force $App -ErrorAction SilentlyContinue
if (Test-Path $App) { Die "Close PokeBrawl first, then run this again." }
Move-Item $top.FullName $App
$sha = "unknown"
$verFile = Join-Path $App "VERSION"
if ($Local -and (Test-Path $verFile)) { $sha = ((Get-Content $verFile -Raw) -split "\s+")[0] }
elseif ($Local) { $sha = "local" }
else { try { $sha = (Invoke-RestMethod -UseBasicParsing -ErrorAction Stop "https://api.github.com/repos/$OwnerRepo/commits/$Branch").sha } catch { } }
Set-Content -Path (Join-Path $App "VERSION") -Value "$sha $(Get-Date -Format 'MMM dd')" -Encoding ascii
$new = $sha -replace '^(.{7}).*', '$1'
if ($old -eq "none") { } elseif ($old -eq $new) { Say "Already up to date ($new)" } else { Say "Updated $old -> $new" }

# --- 3. python environment ----------------------------------------------------------------------------------------
if (-not (Test-Path $VPy)) {
    Say "Creating Python environment..."
    & $Py -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Die "Couldn't create the Python environment" }
}
# the game's folder is always importable, so `python -m pokebrawl` works from anywhere
$site = Join-Path $Venv "Lib\site-packages"
Set-Content -Path (Join-Path $site "pokebrawl-app.pth") -Value $App -Encoding ascii
Say "Installing game engine (pygame-ce)..."
Quiet { & $VPy -m pip install --quiet --disable-pip-version-check --upgrade pip }
& $VPy -m pip install --quiet --disable-pip-version-check --upgrade -r (Join-Path $App "requirements.txt")
if ($LASTEXITCODE -ne 0) { Die "Couldn't install pygame-ce" }

# --- 4. the `pokebrawl` command + shortcuts -----------------------------------------------------------------------
$cmd = @"
@echo off
set PYTHONUTF8=1
if /i "%~1"=="update" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/$OwnerRepo/HEAD/install.ps1 | iex"
  exit /b %ERRORLEVEL%
)
"$VPy" -X utf8 -m pokebrawl %*
"@
Set-Content -Path (Join-Path $Bin "pokebrawl.cmd") -Value $cmd -Encoding ascii
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
if (($userPath -split ";") -notcontains $Bin) {
    [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $Bin).TrimStart(";"), "User")
}
if (($env:Path -split ";") -notcontains $Bin) { $env:Path = "$env:Path;$Bin" }

$ico = Join-Path $Root "pokebrawl.ico"
Quiet { & $VPy -X utf8 -m pokebrawl.winicon $ico }
$shell = New-Object -ComObject WScript.Shell
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "PokeBrawl.lnk"
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "PokeBrawl.lnk"
foreach ($path in @($startMenu, $desktop)) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $VPyW
    $lnk.Arguments = "-X utf8 -m pokebrawl"
    $lnk.WorkingDirectory = $Root
    $lnk.Description = "PokeBrawl"
    if (Test-Path $ico) { $lnk.IconLocation = $ico }
    $lnk.Save()
}

# --- 5. optional: ffmpeg for recording showcase videos ------------------------------------------------------------
$haveFfmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
              (Test-Path (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\ffmpeg.exe"))
if (-not $haveFfmpeg) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say "Installing ffmpeg (for recording showcase MP4s)..."
        winget install --id Gyan.FFmpeg -e --silent --accept-source-agreements --accept-package-agreements | Out-Null
        if ($LASTEXITCODE -ne 0) { Warn "ffmpeg install failed - recording videos won't work until you run: winget install ffmpeg" }
    } else {
        Say "Skipping video recording (needs winget). Everything else works - the Record buttons are just hidden."
    }
}

# --- 6. download the Pokedex + sprites ----------------------------------------------------------------------------
Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
Say "Downloading all Pokemon, moves and sprites (one time, ~20 MB)..."
if (-not $env:POKEBRAWL_SKIP_DOWNLOAD) {
    & $VPy -X utf8 -m pokebrawl download
    if ($LASTEXITCODE -ne 0) { Warn "Couldn't download the Pokemon data right now - the game will retry when you open it." }
}

Write-Host ""
Say "PokeBrawl is installed! Version $new"
Write-Host "   Play:        double-click PokeBrawl on your Desktop (or Start menu), or type: pokebrawl"
Write-Host "   Update:      pokebrawl update"
Write-Host "   (open a new PowerShell/Command Prompt window first so the 'pokebrawl' command is found)"
