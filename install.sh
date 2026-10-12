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

# --- 1. git + python -----------------------------------------------------------------
if [ "$OS" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then
  say "Installing Apple Command Line Tools (gives you git + python3)..."
  xcode-select --install || true
  die "Finish the Command Line Tools install in the popup window, then run this command again."
fi
command -v git >/dev/null 2>&1 || die "git is required (macOS: xcode-select --install)"

PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$(command -v "$cand")"; break
  fi
done
[ -n "$PY" ] || die "Python 3.9+ is required. Install it from https://www.python.org/downloads/ or: brew install python"
say "Using $("$PY" --version) at $PY"

# --- 2. get the game -----------------------------------------------------------------
mkdir -p "$ROOT"
if [ -d "$APP/.git" ]; then
  say "Updating PokeBrawl..."
  git -C "$APP" fetch --depth 1 origin ${BRANCH:+"$BRANCH"} >/dev/null 2>&1 || warn "couldn't fetch updates"
  git -C "$APP" reset --hard FETCH_HEAD >/dev/null 2>&1 || true
else
  say "Downloading PokeBrawl..."
  rm -rf "$APP"
  git clone --depth 1 ${BRANCH:+-b "$BRANCH"} "$REPO" "$APP" >/dev/null 2>&1 \
    || die "Couldn't download $REPO (if the repo is private, the owner needs to make it public or add you)."
fi

# --- 3. python environment -----------------------------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
  say "Creating Python environment..."
  "$PY" -m venv "$VENV"
fi
say "Installing game engine (pygame-ce)..."
"$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
"$VENV/bin/python" -m pip install --quiet --upgrade -r "$APP/requirements.txt"

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
    warn "ffmpeg not found - install it later to record showcase MP4s (https://brew.sh then: brew install ffmpeg)"
  fi
fi

# --- 7. download the Pokedex + sprites -----------------------------------------------
say "Downloading all Pokemon, moves and sprites (one time, ~20 MB)..."
"$BIN/pokebrawl" download

echo
say "PokeBrawl is installed!"
echo "   Play:        pokebrawl            (or open PokeBrawl in ~/Applications)"
echo "   Update:      pokebrawl update"
echo "   Showcase:    pokebrawl showcase $APP/showcases/gen1_vs_gen3.json --record gen1v3.mp4"
echo "   Relay:       pokebrawl relay      (on a server, so friends can play without port forwarding)"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "   (open a new terminal window first so the 'pokebrawl' command is found)";; esac
