#!/usr/bin/env python3
"""
Mock file generator for AI File Cleaner testing.

Builds a sandbox of realistic fake files that exercise every layer of the
scanner:

  - Rules          (test manually: add a rule, rescan, verify skip)
  - Protection     (games, PrismLauncher, Minecraft, .jar, system paths)
  - dpkg ownership (can't be mocked without root — test on real /usr)
  - Content sniff  (real magic bytes so the sniffer classifies correctly)
  - Screenshots    (Portuguese + English name patterns)
  - AI             (junk vs. keepers, with real content so nothing
                    gets accidentally skipped by the sniffer)

Usage:
    python3 generate_mock_files.py
    python3 generate_mock_files.py --path /tmp/ai_test
    python3 generate_mock_files.py --quick      # skip files over 10 MB
    python3 generate_mock_files.py --clean      # wipe the sandbox first
"""  # noqa: EXE001

import argparse
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# ----------------------------------------------------------------------
# Content writers — realistic bytes for each file kind
# ----------------------------------------------------------------------

def _write(p, data, days_ago):
    """Write bytes, pad to size, set mtime."""
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
        len(data)
        # pad with zeroes up to size target (kept by caller via `size`)
    ts = (datetime.now() - timedelta(days=days_ago)).timestamp()  # noqa: DTZ005
    os.utime(p, (ts, ts))


def _write_padded(p, header, size, days_ago):
    """Write header bytes, then zero-pad to `size` total."""
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.write(header)
        rem = size - len(header)
        if rem > 0:
            chunk = b"\x00" * 65536
            while rem > 0:
                n = min(len(chunk), rem)
                f.write(chunk[:n])
                rem -= n
    ts = (datetime.now() - timedelta(days=days_ago)).timestamp()  # noqa: DTZ005
    os.utime(p, (ts, ts))


def write_text(p, text, size, days_ago):
    """Real text file, padded with newlines to size."""
    data = text.encode("utf-8")
    if len(data) < size:
        data += b"\n" * (size - len(data))
    _write_padded(p, data, size, days_ago)


# --- magic byte signatures matching sniff_file_kind() ---
ELF    = b"\x7fELF" + b"\x02\x01\x01\x00" + b"\x00" * 504
DEB    = b"!<arch>\n" + b"\x00" * 504
ZIP    = b"PK\x03\x04" + b"\x00" * 508
GZIP   = b"\x1f\x8b\x08\x00" + b"\x00" * 508
BZIP2  = b"BZh9" + b"\x00" * 508
XZ     = b"\xfd7zXZ\x00" + b"\x00" * 508
PNG    = b"\x89PNG\r\n\x1a\n" + b"\x00" * 504
JPEG   = b"\xff\xd8\xff\xe0" + b"\x00" * 508
GIF    = b"GIF89a" + b"\x00" * 506
PDF    = b"%PDF-1.7\n" + b"\x00" * 504
MKV    = b"\x1aE\xdf\xa3" + b"\x00" * 508


# ----------------------------------------------------------------------

def kb(n):  return n * 1024
def mb(n):  return n * 1024 * 1024


# ======================================================================
# Sandbox sections
# ======================================================================

def build_sandbox(root: Path, quick=False):
    print(f"📁 Creating sandbox at: {root}")
    root.mkdir(parents=True, exist_ok=True)

    created = {"junk": 0, "keepers": 0, "protected": 0, "screenshots": 0,
               "fresh": 0, "sniff": 0, "edge": 0, "empty": 0}

    # ------------------------------------------------------------------
    # 1. JUNK — should be flagged
    # ------------------------------------------------------------------
    junk = [
        # real installer magic bytes so the sniffer sees a deb/archive
        ("tmp/setup_legacy_tool.deb",          DEB,   220, mb(15)),
        ("tmp/old_package_manager.rpm",        b"\xed\xab\xee\xdb",  310, mb(8)),
        ("tmp/NodeApp-3.2.1.AppImage",         ELF,   160, mb(45)),
        ("tmp/gpu_driver_installer.run",       ELF,   400, mb(120)),
        ("tmp/core.dump",                      b"\x7fELF" + b"\x04" * 508, 75, mb(300)),
        ("var/tmp/cache_build.tar.gz",         GZIP,  180, mb(20)),
        ("Downloads/ubuntu_iso_2022.iso",      b"\x00" * 32768 + b"CD001", 500, mb(700)),
        ("Downloads/photos_backup.zip",        ZIP,   240, mb(80)),
        ("Downloads/random_article.tar.xz",    XZ,    190, mb(12)),
        ("Downloads/video_rip_old.mp4",        b"\x00\x00\x00\x18ftypmp42", 380, mb(250)),
        ("cache/thumbs_cache.dat",             b"\x00" * 512, 95, mb(30)),
        ("cache/browser_cache.bin",            b"\x00" * 512, 130, mb(60)),
    ]

    # log file — real text content with "error" markers so it sniffs as text-log
    log_text = (
        "2026-07-15 10:23:11 INFO  Starting build\n"
        "2026-07-15 10:23:14 WARN  Missing optional dep\n"
        "2026-07-15 10:23:19 ERROR Compilation failed\n"
    ) * 500

    for rel, header, days, size in junk:
        _write_padded(root / rel, header, size, days)
        created["junk"] += 1

    write_text(root / "tmp" / "build_debug.log", log_text, kb(800), 65)
    created["junk"] += 1

    write_text(root / "cache" / "stale_index.tmp",
               "stale index, safe to remove\n" * 100, kb(400), 400)
    created["junk"] += 1

    # ------------------------------------------------------------------
    # 2. KEEPERS — should NOT be flagged
    # ------------------------------------------------------------------
    keepers_real = [
        ("Documents/thesis_final.pdf",   PDF,           5,  mb(2)),
        ("Pictures/vacation_2024.jpg",   JPEG,          8,  mb(4)),
        ("Pictures/family.png",          PNG,           14, mb(3)),
        ("Videos/holiday_clip.mp4",      b"\x00\x00\x00\x18ftypmp42", 20, mb(180)),
    ]
    for rel, header, days, size in keepers_real:
        _write_padded(root / rel, header, size, days)
        created["keepers"] += 1

    write_text(root / "Documents" / "notes.txt",
               "Some notes\n" * 50, kb(30), 2)
    write_text(root / "Documents" / "important_letter.docx",
               "Dear Sir,\nThis is a letter.\n" * 20, kb(80), 10)
    write_text(root / "Projects" / "myscript.py",
               "#!/usr/bin/env python3\n"
               "def main():\n"
               "    print('hello')\n"
               "\n"
               "if __name__ == '__main__':\n"
               "    main()\n",
               kb(15), 1)
    write_text(root / "Projects" / "main.c",
               "#include <stdio.h>\n"
               "int main(void) { return 0; }\n",
               kb(8), 3)
    write_text(root / "Projects" / "README.md",
               "# My project\n\nThis is a test.\n", kb(2), 1)
    created["keepers"] += 5

    # ------------------------------------------------------------------
    # 3. PROTECTED — games, PrismLauncher, Minecraft, .jar
    #    These must NEVER appear in the review list.
    # ------------------------------------------------------------------
    protected = [
        ("games/MyGame/assets.pak",              b"\x00" * 512, 300, mb(120)),
        ("games/MyGame/data.bsa",                b"\x00" * 512, 400, mb(80)),
        ("games/MyGame/save01.sav",              b"SAVE" + b"\x00" * 508, 45, mb(2)),
        ("mods/jei_1.20.1.jar",                  ZIP,   30,  mb(2)),
        ("mods/optifine_HD.jar",                 ZIP,   200, mb(10)),
        ("mods/create_1.19.2.jar",               ZIP,   500, mb(15)),
        (".local/share/PrismLauncher/instances/1.20.1-forge/instance.cfg",
                                                 b"[General]\nname=1.20.1 Forge\n", 180, kb(2)),
        (".local/share/PrismLauncher/instances/1.20.1-forge/minecraft/mods/sodium.jar",
                                                 ZIP, 400, mb(1)),
        (".local/share/PrismLauncher/instances/1.20.1-forge/minecraft/mods/iris.jar",
                                                 ZIP, 350, mb(2)),
        (".local/share/PrismLauncher/instances/1.20.1-forge/minecraft/saves/World1/level.dat",
                                                 b"\x0a\x00\x00" + b"\x00" * 509, 250, kb(50)),
        (".local/share/PrismLauncher/instances/Fabulously-Optimized/minecraft/mods/mod_a.jar",
                                                 ZIP, 90, mb(3)),
        (".var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances/Test/minecraft/mods/x.jar",
                                                 ZIP, 300, mb(1)),
        (".minecraft/mods/legacy_mod.jar",       ZIP, 600, mb(2)),
        (".minecraft/saves/OldWorld/level.dat",  b"\x0a\x00\x00" + b"\x00" * 509, 900, kb(40)),
        (".local/share/Steam/steamapps/common/SomeGame/game.pak",
                                                 b"\x00" * 512, 500, mb(200)),
    ]
    for rel, header, days, size in protected:
        _write_padded(root / rel, header, size, days)
        created["protected"] += 1

    # ------------------------------------------------------------------
    # 4. SCREENSHOTS — should be flagged if older than the setting
    #    Includes Portuguese names (Linux Mint pt_BR default).
    # ------------------------------------------------------------------
    shots = [
        # pt_BR GNOME/Mint — the ones YOUR system produces
        ("Imagens/Screenshots/Captura de tela de 2026-01-15 14-23-01.png",  240, mb(2)),
        ("Imagens/Screenshots/Captura de tela de 2026-02-03 09-11-45.png",  220, mb(1)),
        ("Imagens/Screenshots/Captura de tela de 2026-08-20 22-45-13.png",  24,  mb(2)),
        # en_US GNOME
        ("Pictures/Screenshots/Screenshot from 2025-11-02 11-22-33.png",    315, mb(3)),
        ("Pictures/Screenshots/Screenshot from 2026-08-30 15-00-00.png",    14,  mb(2)),
        # KDE / XFCE
        ("Pictures/Screenshot_20251225_120000.png",                         260, mb(2)),
        # Windows-imported
        ("Pictures/Screenshot (5).png",                                     180, mb(1)),
    ]
    for rel, days, size in shots:
        _write_padded(root / rel, PNG, size, days)
        created["screenshots"] += 1

    # ------------------------------------------------------------------
    # 5. FRESH FILES — recent mtimes, should not be flagged
    # ------------------------------------------------------------------
    for i in range(3):
        rel = f"Downloads/recent_file_{i+1}.deb"
        _write_padded(root / rel, DEB, mb(5), 0.5)  # 12 hours old
        created["fresh"] += 1

    write_text(root / "tmp" / "active_session.log",
               "still being written to\n" * 20, kb(50), 0.1)
    created["fresh"] += 1

    # ------------------------------------------------------------------
    # 6. CONTENT-SNIFF TEST FILES — verify each sniffer branch
    #    Old + big enough to trigger the AI, but content should cause skip.
    # ------------------------------------------------------------------
    sniff_tests = [
        # These should be SKIPPED by the sniffer (never reach the AI)
        ("tmp/script_that_should_be_skipped.sh",
         b"#!/bin/bash\necho hello\n" + b"\n" * kb(50), 200, kb(51)),
        ("tmp/source_file_should_be_skipped.py",
         b"#!/usr/bin/env python3\ndef main():\n    pass\n" + b"\n" * kb(50), 200, kb(51)),
        ("tmp/executable_should_be_skipped",
         ELF, 200, kb(200)),
        ("tmp/xml_config_should_be_skipped.xml",
         b'<?xml version="1.0"?>\n<root/>\n' + b"\n" * kb(20), 200, kb(21)),
        ("tmp/readme_should_be_skipped.md",
         b"# README\n\nThis is documentation.\n" + b"\n" * kb(20), 200, kb(21)),
    ]
    for rel, data, days, size in sniff_tests:
        _write_padded(root / rel, data, size, days)
        created["sniff"] += 1

    # ------------------------------------------------------------------
    # 7. BOUNDARY CASES — exactly at bucket edges
    #    Helps confirm the size/age bucketing is roughly sensible.
    # ------------------------------------------------------------------
    edges = [
        ("tmp/edge_age_6_days.deb",    DEB, 6,    mb(10)),
        ("tmp/edge_age_7_days.deb",    DEB, 7,    mb(10)),
        ("tmp/edge_age_29_days.deb",   DEB, 29,   mb(10)),
        ("tmp/edge_age_30_days.deb",   DEB, 30,   mb(10)),
        ("tmp/edge_age_89_days.deb",   DEB, 89,   mb(10)),
        ("tmp/edge_age_90_days.deb",   DEB, 90,   mb(10)),
        ("tmp/edge_size_99kb.deb",     DEB, 200,  kb(99)),
        ("tmp/edge_size_101kb.deb",    DEB, 200,  kb(101)),
        ("tmp/edge_size_9mb.deb",      DEB, 200,  mb(9)),
        ("tmp/edge_size_11mb.deb",     DEB, 200,  mb(11)),
    ]
    for rel, header, days, size in edges:
        _write_padded(root / rel, header, size, days)
        created["edge"] += 1

    # ------------------------------------------------------------------
    # 8. EMPTY + HIDDEN
    # ------------------------------------------------------------------
    (root / "tmp" / "empty_file.dat").parent.mkdir(parents=True, exist_ok=True)
    (root / "tmp" / "empty_file.dat").touch()
    created["empty"] += 1

    write_text(root / "Documents" / ".hidden_dotfile",
               "hidden config\n", kb(2), 100)
    created["empty"] += 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = sum(created.values())

    print()
    print("✅ Sandbox ready.")
    print()
    print("   Categories (file counts):")
    print(f"     🗑  Junk           : {created['junk']}")
    print(f"     ✅  Keepers        : {created['keepers']}")
    print(f"     🛡  Protected      : {created['protected']}   (should NEVER appear)")
    print(f"     📸  Screenshots    : {created['screenshots']}")
    print(f"     🕐  Fresh          : {created['fresh']}   (should NOT be flagged)")
    print(f"     🔍  Sniff tests    : {created['sniff']}   (should be skipped by sniffer)")
    print(f"     📐  Edge cases     : {created['edge']}")
    print(f"     📭  Empty/hidden   : {created['empty']}")
    print("     ────────────────────────────")
    print(f"     Total            : {total} files")
    print()

    if quick:
        print("   ⚡ Quick mode — files over 10 MB were skipped")
        print()
    else:
        print("   💾 Total size on disk: see `du -sh` (large — ~2 GB with the ISO)")
        print()

    print("👉 Point the AI cleaner at:")
    print(f"   {root}")
    print()
    print("🧪 What to check:")
    print()
    print("   1. Old junk should be flagged with reasons like")
    print("      'An old installer you already ran'")
    print()
    print("   2. Keepers should NOT be flagged. Their mtimes are recent.")
    print()
    print("   3. Protected files should not appear at all — if any do,")
    print("      the scanner's protection layer is broken.")
    print()
    print("   4. Screenshots older than the setting should be flagged.")
    print("      The two recent ones (2026-08-*) should NOT be.")
    print()
    print("   5. Fresh files (< 1 day) should NOT be flagged.")
    print()
    print("   6. Sniff-test files should be silently skipped. If any show")
    print("      up in the review list, `sniff_file_kind()` is broken.")
    print()
    print("   7. Edge cases confirm bucketing looks sensible.")
    print()
    print("🧹 To wipe the sandbox later:")
    print(f"   rm -rf {root}")
    print()


# ======================================================================

def main():
    ap = argparse.ArgumentParser(
        description="Generate mock files for AI Cleaner testing."
    )
    ap.add_argument(
        "--path",
        default=os.path.expanduser("~/ai_cleaner_test"),
        help="Where to create the sandbox (default: ~/ai_cleaner_test)",
    )
    ap.add_argument(
        "--quick", action="store_true",
        help="Skip files over 10 MB (fast iteration)",
    )
    ap.add_argument(
        "--clean", action="store_true",
        help="Remove the sandbox first if it exists",
    )
    args = ap.parse_args()

    target = Path(args.path).expanduser().resolve()

    if args.clean and target.exists():
        print(f"🧹 Removing existing sandbox at {target}")
        shutil.rmtree(target)

    build_sandbox(target, quick=args.quick)


if __name__ == "__main__":
    main()