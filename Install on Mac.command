#!/bin/bash
# Double-click to install/update PokeBrawl from this folder (if macOS blocks it: right-click > Open).
cd "$(dirname "$0")" && bash ./install.sh
echo; read -r -p "Done - press Enter to close this window. " _
