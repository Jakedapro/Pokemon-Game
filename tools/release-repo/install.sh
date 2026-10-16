#!/usr/bin/env bash
# PokeBrawl installer for Mac:
#
#   curl -fsSL https://raw.githubusercontent.com/Jakedapro/PokeBrawl/HEAD/install.sh | bash
#
# Downloads the PokeBrawl app for your Mac (Apple Silicon or Intel) into ~/Applications and adds a `pokebrawl`
# command. Re-running it updates the game. Your save in ~/.pokebrawl is never touched.
set -euo pipefail

REPO="Jakedapro/PokeBrawl"
DEST="$HOME/Applications"
BIN="$HOME/.local/bin"

say()  { printf "\033[1;31m==>\033[0m \033[1m%s\033[0m\n" "$*"; }
die()  { printf "\033[1;31mError:\033[0m %s\n" "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || die "This installer is for Mac. On Windows use install.ps1 (see the README)."
case "$(uname -m)" in
  arm64) ASSET="PokeBrawl-mac-arm64.zip" ;;
  *)     # an Intel build running under Rosetta still reports x86_64: check the real chip
         if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" = "1" ]; then ASSET="PokeBrawl-mac-arm64.zip"
         else ASSET="PokeBrawl-mac-intel.zip"; fi ;;
esac

URL="https://github.com/$REPO/releases/latest/download/$ASSET"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
say "Downloading PokeBrawl ($ASSET)..."
curl -fL --progress-bar "$URL" -o "$TMP/$ASSET" || die "Couldn't download $URL (check your internet)."
ditto -x -k "$TMP/$ASSET" "$TMP/out" || die "The download looks broken - try again."
[ -d "$TMP/out/PokeBrawl.app" ] || die "The download looks wrong - try again."

mkdir -p "$DEST"
pkill -f "PokeBrawl.app/Contents/MacOS/" 2>/dev/null || true
rm -rf "$DEST/PokeBrawl.app"
mv "$TMP/out/PokeBrawl.app" "$DEST/PokeBrawl.app"
xattr -dr com.apple.quarantine "$DEST/PokeBrawl.app" 2>/dev/null || true

# the `pokebrawl` command (replaces the old Python-based one if you had it)
mkdir -p "$BIN"
cat > "$BIN/pokebrawl" <<EOF
#!/bin/bash
exec "$DEST/PokeBrawl.app/Contents/MacOS/PokeBrawl" "\$@"
EOF
chmod +x "$BIN/pokebrawl"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) grep -qs 'pokebrawl-path' "$HOME/.zshrc" || printf '\nexport PATH="$HOME/.local/bin:$PATH"  # pokebrawl-path\n' >> "$HOME/.zshrc" ;;
esac
rm -rf "$HOME/.pokebrawl/app" "$HOME/.pokebrawl/venv" "$HOME/.pokebrawl/python"   # the old Python install, if any

say "PokeBrawl is installed! $("$DEST/PokeBrawl.app/Contents/MacOS/PokeBrawl" version 2>/dev/null || true)"
echo "   Play: open PokeBrawl from ~/Applications (or Launchpad / Spotlight), or type: pokebrawl"
echo "   It updates itself. Running this command again also updates it."
open "$DEST/PokeBrawl.app" || true
