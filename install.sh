#!/usr/bin/env bash
# PokeBrawl one-command installer (macOS, also works on Linux).
#
#   curl -fsSL https://raw.githubusercontent.com/jamalmusialla81-hub/Pokemon-Game/HEAD/install.sh | bash
#
# Installs into ~/.pokebrawl, adds a `pokebrawl` command and a PokeBrawl app in ~/Applications.
# Re-running it updates the game.
set -euo pipefail

REPO="${POKEBRAWL_REPO:-https://github.com/jamalmusialla81-hub/Pokemon-Game.git}"
BRANCH="${POKEBRAWL_BRANCH:-}"
ROOT="${POKEBRAWL_HOME:-$HOME/.pokebrawl}"
APP="$ROOT/app"
VENV="$ROOT/venv"
BIN="$HOME/.local/bin"

say()  { printf "\033[1;31m==>\033[0m \033[1m%s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m!!\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31mError:\033[0m %s\n" "$*" >&2; exit 1; }

OS="$(uname -s)"

# --- 0. HTTPS trust ------------------------------------------------------------------
# On networks/Macs that inspect HTTPS (school or work Wi-Fi, managed Macs, some antivirus), curl/git/pip
# don't trust the inspection certificate even though the Mac's Keychain does. If GitHub can't be verified,
# export the Keychain's trusted certificates and use them for every download in this install.
mkdir -p "$ROOT"
if ! curl -fsS --max-time 15 https://github.com >/dev/null 2>&1; then
  if [ "$OS" = "Darwin" ] && command -v security >/dev/null 2>&1; then
    warn "HTTPS check failed - using the certificates your Mac's Keychain trusts"
    PEM="$ROOT/keychain-certs.pem"
    security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain \
      /Library/Keychains/System.keychain "$HOME/Library/Keychains/login.keychain-db" > "$PEM" 2>/dev/null || true
    if [ -s "$PEM" ] && curl -fsS --max-time 15 --cacert "$PEM" https://github.com >/dev/null 2>&1; then
      export CURL_CA_BUNDLE="$PEM" GIT_SSL_CAINFO="$PEM" PIP_CERT="$PEM" SSL_CERT_FILE="$PEM" REQUESTS_CA_BUNDLE="$PEM"
    else
      die "Can't make a secure connection to GitHub. Check your Mac's date & time is set automatically
       (System Settings > General > Date & Time), or try another network (e.g. a phone hotspot)."
    fi
  fi
fi

# --- 1. tools (no Apple Command Line Tools needed) -------------------------------------
# Without the Command Line Tools, /usr/bin/git and /usr/bin/python3 are stubs that pop up an install dialog,
# so we never run them. Instead: no git -> download the code as an archive; no Python -> download a
# self-contained Python just for PokeBrawl into ~/.pokebrawl/python.
HAS_CLT=1
if [ "$OS" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then HAS_CLT=0; fi
usable() {  # usable <command>: exists and isn't a Command Line Tools stub
  local p; p="$(command -v "$1" 2>/dev/null)" || return 1
  if [ "$HAS_CLT" = 0 ] && { [ "$p" = "/usr/bin/git" ] || [ "$p" = "/usr/bin/python3" ]; }; then return 1; fi
  return 0
}
GIT=""
if [ -z "${POKEBRAWL_NO_GIT:-}" ] && usable git; then GIT="$(command -v git)"; fi

OWNER_REPO="$(printf '%s' "$REPO" | sed -E 's#^https://github.com/##; s#\.git$##')"
STANDALONE="$ROOT/python/bin/python3"

download_python() {
  local arch os_tag url
  arch="$(uname -m)"; [ "$arch" = "arm64" ] && arch="aarch64"
  if [ "$OS" = "Darwin" ]; then os_tag="apple-darwin"; else os_tag="unknown-linux-gnu"; fi
  say "Downloading a private copy of Python for PokeBrawl (one time, ~20 MB)..."
  url="${POKEBRAWL_PYTHON_URL:-}"
  if [ -z "$url" ]; then
    url="$(curl -fsSL https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest 2>/dev/null \
      | grep -o "https://[^\"]*cpython-3\.12\.[0-9]*+[0-9]*-$arch-$os_tag-install_only\.tar\.gz" | head -1 || true)"
  fi
  if [ -z "$url" ]; then
    url="https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.12.7+20241016-$arch-$os_tag-install_only.tar.gz"
  fi
  rm -rf "$ROOT/python"
  curl -fsSL "$url" | tar -xz -C "$ROOT" || die "Couldn't download Python ($url)"
  [ -x "$STANDALONE" ] || die "Python download looks broken ($url)"
}

PY=""
if [ -x "$STANDALONE" ]; then
  PY="$STANDALONE"
elif [ -z "${POKEBRAWL_FORCE_STANDALONE:-}" ]; then
  for cand in python3.12 python3.13 python3.11 python3.10 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3 \
              /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 python3; do
    if usable "$cand" && "$cand" -c 'import sys; sys.exit(0 if (3, 9) <= sys.version_info < (3, 14) else 1)' 2>/dev/null; then
      PY="$(command -v "$cand")"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  download_python
  PY="$STANDALONE"
fi
say "Using $("$PY" --version) at $PY"

# --- 2. get the game -----------------------------------------------------------------
mkdir -p "$ROOT"
version_of() {  # short version of the installed copy
  if [ -d "$APP/.git" ] && [ -n "$GIT" ]; then git -C "$APP" rev-parse --short HEAD 2>/dev/null || echo none
  elif [ -f "$APP/VERSION" ]; then cut -c1-7 "$APP/VERSION"
  else echo none; fi
}
fetch_archive() {  # download the code without git
  local tmp sha url
  tmp="$(mktemp -d)"
  url="${POKEBRAWL_ARCHIVE_URL:-https://github.com/$OWNER_REPO/archive/${BRANCH:-HEAD}.tar.gz}"
  curl -fsSL "$url" | tar -xz -C "$tmp" || die "Couldn't download $url (check your internet)"
  rm -rf "$APP"
  mv "$tmp"/*/ "$APP"
  rmdir "$tmp" 2>/dev/null || true
  sha="${POKEBRAWL_ARCHIVE_SHA:-$(curl -fsSL "https://api.github.com/repos/$OWNER_REPO/commits/${BRANCH:-HEAD}" 2>/dev/null \
        | grep -m1 '"sha"' | sed -E 's/.*"sha": *"([0-9a-f]+)".*/\1/' || true)}"
  printf '%s %s\n' "${sha:-unknown}" "$(date '+%b %d')" > "$APP/VERSION"
}
fresh_clone() {
  rm -rf "$APP"
  git clone --depth 1 ${BRANCH:+-b "$BRANCH"} "$REPO" "$APP" \
    || die "Couldn't download $REPO (check your internet; the repo must be public)."
}
OLD="$(version_of)"
rm -rf "$APP.new" "$APP.old" "$APP.download"  # leftovers from the in-game auto-updater
if [ -d "$APP/.git" ] && [ -n "$GIT" ]; then
  say "Updating PokeBrawl..."
  git -C "$APP" remote set-url origin "$REPO"
  if git -C "$APP" fetch --depth 1 origin ${BRANCH:+"$BRANCH"} && git -C "$APP" reset --hard FETCH_HEAD >/dev/null; then
    :
  else
    warn "Updating in place failed - downloading a fresh copy instead"
    fresh_clone
  fi
elif [ -n "$GIT" ]; then
  say "Downloading PokeBrawl..."
  fresh_clone
else
  [ -d "$APP" ] && say "Updating PokeBrawl..." || say "Downloading PokeBrawl..."
  fetch_archive
fi
NEW="$(version_of)"
if [ "$OLD" = "none" ]; then :; elif [ "$OLD" = "$NEW" ]; then say "Already up to date ($NEW)"; else say "Updated $OLD -> $NEW"; fi

# --- 3. python environment -----------------------------------------------------------
make_venv() {
  rm -rf "$VENV"
  "$PY" -m venv "$VENV"
}
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
  say "Creating Python environment..."
  make_venv
fi
say "Installing game engine (pygame-ce)..."
"$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
if ! "$VENV/bin/python" -m pip install --quiet --upgrade -r "$APP/requirements.txt"; then
  if [ "$PY" != "$STANDALONE" ]; then
    warn "Your Python couldn't install the game engine - switching to PokeBrawl's own Python"
    download_python
    PY="$STANDALONE"
    make_venv
    "$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
    "$VENV/bin/python" -m pip install --quiet --upgrade -r "$APP/requirements.txt" || die "Couldn't install pygame-ce"
  else
    die "Couldn't install pygame-ce"
  fi
fi

# --- 4. launcher ---------------------------------------------------------------------
mkdir -p "$BIN"
cat > "$BIN/pokebrawl" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$APP\${PYTHONPATH:+:\$PYTHONPATH}"
if [ "\${1:-}" = "update" ]; then
  exec bash -c "curl -fsSL https://raw.githubusercontent.com/jamalmusialla81-hub/Pokemon-Game/HEAD/install.sh | bash"
fi
exec "$VENV/bin/python" -m pokebrawl "\$@"
EOF
chmod +x "$BIN/pokebrawl"

case ":$PATH:" in
  *":$BIN:"*) ;;
  *)
    for rc in "$HOME/.zshrc" "$HOME/.bash_profile"; do
      if [ -f "$rc" ] || [ "$rc" = "$HOME/.zshrc" ]; then
        grep -qs 'pokebrawl-path' "$rc" || printf '\nexport PATH="$HOME/.local/bin:$PATH"  # pokebrawl-path\n' >> "$rc"
      fi
    done
    export PATH="$BIN:$PATH"
    ;;
esac

# --- 5. Mac app (double-click to play) -----------------------------------------------
if [ "$OS" = "Darwin" ]; then
  APPDIR="$HOME/Applications/PokeBrawl.app"
  mkdir -p "$APPDIR/Contents/MacOS"
  cat > "$APPDIR/Contents/MacOS/PokeBrawl" <<EOF
#!/bin/bash
exec "$BIN/pokebrawl"
EOF
  chmod +x "$APPDIR/Contents/MacOS/PokeBrawl"
  cat > "$APPDIR/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>PokeBrawl</string>
  <key>CFBundleExecutable</key><string>PokeBrawl</string>
  <key>CFBundleIdentifier</key><string>local.pokebrawl</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1.0</string>
</dict></plist>
EOF
fi

# --- 6. optional: ffmpeg for recording showcase videos -------------------------------
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    say "Installing ffmpeg (for recording showcase MP4s)..."
    brew install ffmpeg >/dev/null 2>&1 || warn "ffmpeg install failed - recording videos won't work until you: brew install ffmpeg"
  else
    say "Skipping video recording (needs Homebrew). Everything else works - the Record buttons are just hidden."
  fi
fi

# --- 7. download the Pokedex + sprites -----------------------------------------------
say "Downloading all Pokemon, moves and sprites (one time, ~20 MB)..."
if [ -n "${POKEBRAWL_SKIP_DOWNLOAD:-}" ]; then
  :
elif ! "$BIN/pokebrawl" download; then
  warn "Couldn't download the Pokemon data right now - the game will retry when you open it."
fi

echo
say "PokeBrawl is installed! Version $(version_of)"
echo "   Play:        pokebrawl            (or open PokeBrawl in ~/Applications)"
echo "   Update:      pokebrawl update"
echo "   Showcase:    pokebrawl showcase $APP/showcases/gen1_vs_gen3.json --record gen1v3.mp4"
echo "   Relay:       pokebrawl relay      (on a server, so friends can play without port forwarding)"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "   (open a new terminal window first so the 'pokebrawl' command is found)";; esac
