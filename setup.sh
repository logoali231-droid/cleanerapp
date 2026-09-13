#!/usr/bin/env bash
# Installer for AI File Cleaner — makes it appear in the Linux Mint menu
set -e

APP_ID="ai-file-cleaner"
APP_NAME="AI File Cleaner"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# find the python file (either name)
SRC_APP=""
for candidate in "ai_cleaner_wizard.py" "ai_cleaner_rl.py"; do
    if [ -f "$SRC_DIR/$candidate" ]; then SRC_APP="$SRC_DIR/$candidate"; break; fi
done
if [ -z "$SRC_APP" ]; then
    echo "❌ Could not find ai_cleaner_wizard.py in $SRC_DIR"
    exit 1
fi

echo "🔍 Checking dependencies…"
missing=()
python3 -c "import PyQt5" 2>/dev/null || missing+=("python3-pyqt5")
python3 -c "import numpy" 2>/dev/null || missing+=("python3-numpy")

if [ ${#missing[@]} -gt 0 ]; then
    echo "📦 Installing: ${missing[*]}"
    sudo apt update && sudo apt install -y "${missing[@]}"
fi

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/$APP_ID"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$BIN_DIR" "$APP_DIR" "$DESKTOP_DIR" "$ICON_DIR"

# ---- app ----
cp "$SRC_APP" "$APP_DIR/ai_cleaner_wizard.py"
chmod +x "$APP_DIR/ai_cleaner_wizard.py"

# ---- launcher ----
cat > "$BIN_DIR/$APP_ID" <<EOF
#!/usr/bin/env bash
exec python3 "$APP_DIR/ai_cleaner_wizard.py" "\$@"
EOF
chmod +x "$BIN_DIR/$APP_ID"

# ---- icon (SVG) ----
cat > "$ICON_DIR/$APP_ID.svg" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4a9eff"/>
      <stop offset="1" stop-color="#2f7ad6"/>
    </linearGradient>
  </defs>
  <rect x="6" y="6" width="116" height="116" rx="26" fill="url(#g)"/>
  <path d="M40 34 L74 34 L88 48 L88 96 L40 96 Z" fill="#ffffff" opacity="0.96"/>
  <path d="M74 34 L74 48 L88 48 Z" fill="#cfdcf0"/>
  <line x1="50" y1="58" x2="78" y2="58" stroke="#cfdcf0" stroke-width="3" stroke-linecap="round"/>
  <line x1="50" y1="68" x2="78" y2="68" stroke="#cfdcf0" stroke-width="3" stroke-linecap="round"/>
  <line x1="50" y1="78" x2="70" y2="78" stroke="#cfdcf0" stroke-width="3" stroke-linecap="round"/>
  <path d="M94 22 L96.5 31 L105.5 33.5 L96.5 36 L94 45 L91.5 36 L82.5 33.5 L91.5 31 Z" fill="#ffd76a"/>
  <path d="M30 78 L31.7 84 L37.7 85.7 L31.7 87.4 L30 93.4 L28.3 87.4 L22.3 85.7 L28.3 84 Z" fill="#ffd76a"/>
</svg>
SVG

# ---- desktop entry ----
cat > "$DESKTOP_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
GenericName=Disk Cleaner
Comment=Find and remove unused files with a friendly AI
Exec=$BIN_DIR/$APP_ID
Icon=$APP_ID
Terminal=false
Categories=Utility;System;FileTools;Qt;
Keywords=cleaner;disk;cleanup;ai;files;junk;space;
StartupNotify=true
StartupWMClass=ai-file-cleaner
EOF
chmod +x "$DESKTOP_DIR/$APP_ID.desktop"

# ---- refresh caches ----
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo ""
echo "✅ Installed!"
echo ""
echo "   ▸ Launch from your menu:  search for \"$APP_NAME\""
echo "   ▸ Or from a terminal:     $APP_ID"
echo "   ▸ For full-system scans:  sudo $APP_ID"
echo ""
echo "   Uninstall:"
echo "     rm $BIN_DIR/$APP_ID"
echo "     rm -r $APP_DIR"
echo "     rm $DESKTOP_DIR/$APP_ID.desktop"
echo "     rm $ICON_DIR/$APP_ID.svg"