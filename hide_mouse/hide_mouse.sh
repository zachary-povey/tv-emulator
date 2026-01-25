#!/bin/bash

# 1. Define Variables
EXT_UUID="hide-cursor@elcste.com"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"
# Get the latest version tag from GNOME extensions website (approximate)
# You might want to pin a specific version URL for stability in your scripts
DOWNLOAD_URL="https://extensions.gnome.org/extension-data/hide-cursor@elcste.v10.shell-extension.zip"

echo ">>> Setting up Hide Cursor extension..."

# 2. Create the directory
mkdir -p "$EXT_DIR"

# 3. Download and Unzip
wget -O /tmp/extension.zip "$DOWNLOAD_URL"
unzip -o /tmp/extension.zip -d "$EXT_DIR"

# 4. Compile the configuration schema
# This is crucial to change settings via CLI later
glib-compile-schemas "$EXT_DIR/schemas/"

echo ">>> Installation complete."
echo ">>> CRITICAL: You must LOG OUT and LOG BACK IN now for GNOME to see the new extension."
echo ">>> After logging back in, run the configuration command below."