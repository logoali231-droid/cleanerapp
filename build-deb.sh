#!/usr/bin/env bash
# build-deb.sh — build a .deb from the current source tree.
set -e

APP_ID="ai-file-cleaner"
APP_NAME="AI File Cleaner"
VERSION="1.0.0"
ARCH="all"
MAINTAINER="dipper <dipper@users.noreply.github.com>"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_SRC="$SRC_DIR/src/ai_cleaner"
SVG_SRC="$SRC_DIR/com.dipper.AIFileCleaner.svg"

if [ ! -d "$PKG_SRC" ]; then
    echo "❌ Could not find $PKG_SRC"
    exit 1
fi
if [ ! -f "$SVG_SRC" ]; then
    echo "❌ Could not find $SVG_SRC"
    exit 1
fi

# ---- staging directory ----
BUILD_ROOT="$(mktemp -d /tmp/deb-build-XXXXXX)"
trap 'rm -rf "$BUILD_ROOT"' EXIT

PKG_ROOT="$BUILD_ROOT/${APP_ID}_${VERSION}_${ARCH}"
mkdir -p "$PKG_ROOT/DEBIAN"
mkdir -p "$PKG_ROOT/usr/bin"
mkdir -p "$PKG_ROOT/usr/share/$APP_ID"
mkdir -p "$PKG_ROOT/usr/share/applications"
mkdir -p "$PKG_ROOT/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$PKG_ROOT/usr/share/doc/$APP_ID"

# ---- DEBIAN/control ----
cat > "$PKG_ROOT/DEBIAN/control" <<EOF
Package: $APP_ID
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.8), python3-pyqt5
Maintainer: $MAINTAINER
Homepage: https://github.com/logoali231-droid/cleanerapp
Description: $APP_NAME - RL-powered file cleaner
 AI File Cleaner scans your files and uses a small reinforcement-learning
 agent to identify unused files and installation leftovers. It shows you
 what it finds, protects your important data, and learns from every
 keep/delete decision you make.
 .
 Features:
  * Reinforcement-learning decisions with dynamic confidence
  * Rule system - teach it once, it remembers
  * Trash-safe deletion - restore from Nemo
  * Protects games, dev folders, system paths
  * Screenshot detection with configurable age
  * Runs entirely on your machine. No network, no cloud.
EOF

# ---- the Python package ----
cp -r "$PKG_SRC" "$PKG_ROOT/usr/share/$APP_ID/ai_cleaner"

# ---- launcher ----
cat > "$PKG_ROOT/usr/bin/$APP_ID" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="/usr/share/$APP_ID:\$PYTHONPATH"
exec python3 -m ai_cleaner "\$@"
EOF
chmod 755 "$PKG_ROOT/usr/bin/$APP_ID"

# ---- desktop entry ----
cat > "$PKG_ROOT/usr/share/applications/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
GenericName=Disk Cleaner
Comment=Find and remove unused files with a friendly AI
Exec=$APP_ID
Icon=$APP_ID
Terminal=false
Categories=Utility;System;FileTools;Qt;
Keywords=cleaner;disk;cleanup;ai;files;junk;space;
StartupNotify=true
StartupWMClass=ai-file-cleaner
EOF
chmod 644 "$PKG_ROOT/usr/share/applications/$APP_ID.desktop"

# ---- icon ----
cp "$SVG_SRC" "$PKG_ROOT/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"

# ---- docs ----
[ -f "$SRC_DIR/README.md" ] && cp "$SRC_DIR/README.md" "$PKG_ROOT/usr/share/doc/$APP_ID/README.md"
[ -f "$SRC_DIR/LICENSE" ]   && cp "$SRC_DIR/LICENSE"   "$PKG_ROOT/usr/share/doc/$APP_ID/copyright"

# ---- postinst: refresh desktop + icon cache ----
cat > "$PKG_ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "$PKG_ROOT/DEBIAN/postinst"

# ---- prerm: refresh desktop cache after removal ----
cat > "$PKG_ROOT/DEBIAN/prerm" <<'EOF'
#!/bin/bash
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database /usr/share/applications || true
    fi
fi
exit 0
EOF
chmod 755 "$PKG_ROOT/DEBIAN/prerm"

# ---- md5sums (dpkg needs these for integrity checking) ----
( cd "$PKG_ROOT" && \
  find . -type f ! -regex './DEBIAN/.*' -printf '%P\0' \
    | xargs -0 -r md5sum > DEBIAN/md5sums )

# ---- build ----
DEB_FILE="$SRC_DIR/${APP_ID}_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$PKG_ROOT" "$DEB_FILE" >/dev/null

echo ""
echo "✅ Built: $(basename "$DEB_FILE")"
echo "   Path : $DEB_FILE"
echo "   Size : $(du -h "$DEB_FILE" | cut -f1)"
echo ""
echo "Inspect contents:"
echo "   dpkg-deb --contents $DEB_FILE"
echo "   dpkg-deb --info     $DEB_FILE"
echo ""
echo "Install:"
echo "   sudo apt install $DEB_FILE"
echo ""
echo "Remove:"
echo "   sudo apt remove $APP_ID"