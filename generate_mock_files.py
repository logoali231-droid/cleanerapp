#!/usr/bin/env python3
"""
Mock file generator for AI File Cleaner testing.
Creates a realistic sandbox of fake files (junk + keepers + protected
game/PrismLauncher data) with backdated timestamps.
No AI involved — just files.
"""

import os
import sys
import random
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# ----------------------------------------------------------------------

def make_file(path: Path, days_ago: float, size_bytes: int):
    """Create a file with a specific mtime (days ago) and size."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        # Write a bit of random-ish data (fast, no need for real content)
        chunk = b"\x42" * 8192
        written = 0
        while written < size_bytes:
            to_write = min(len(chunk), size_bytes - written)
            f.write(chunk[:to_write])
            written += to_write
    ts = (datetime.now() - timedelta(days=days_ago)).timestamp()
    os.utime(path, (ts, ts))
    return path

def kb(n):  return n * 1024
def mb(n):  return n * 1024 * 1024

# ----------------------------------------------------------------------

def build_sandbox(root: Path):
    print(f"📁 Creating sandbox at: {root}")
    root.mkdir(parents=True, exist_ok=True)

    created = []

    # ------------------------------------------------------------------
    # 1. JUNK — should be flagged for deletion by the agent
    # ------------------------------------------------------------------
    junk = [
        # (relative path, days_ago, size)
        ("tmp/setup_legacy_tool.deb",        220, mb(15)),
        ("tmp/old_package_manager.rpm",      310, mb(8)),
        ("tmp/NodeApp-3.2.1.AppImage",       160, mb(45)),
        ("tmp/gpu_driver_installer.run",     400, mb(120)),
        ("tmp/build_debug.log",              65,  kb(800)),
        ("tmp/core.dump",                    75,  mb(300)),
        ("var/tmp/cache_build.tar.gz",       180, mb(20)),
        ("Downloads/ubuntu_iso_2022.iso",    500, mb(700)),
        ("Downloads/photos_backup.zip",      240, mb(80)),
        ("Downloads/random_article.tar.xz",  190, mb(12)),
        ("Downloads/video_rip_old.mp4",      380, mb(250)),
        ("cache/thumbs_cache.dat",           95,  mb(30)),
        ("cache/browser_cache.bin",          130, mb(60)),
        ("cache/stale_index.tmp",            400, kb(400)),
    ]

    # ------------------------------------------------------------------
    # 2. KEEPERS — should NOT be flagged
    # ------------------------------------------------------------------
    keepers = [
        ("Documents/thesis_final.pdf",        5,  mb(2)),
        ("Documents/notes.txt",               2,  kb(30)),
        ("Documents/important_letter.docx",   10, kb(80)),
        ("Pictures/vacation_2024.jpg",        8,  mb(4)),
        ("Pictures/family.png",               14, mb(3)),
        ("Videos/holiday_clip.mp4",           20, mb(180)),
        ("Projects/myscript.py",              1,  kb(15)),
        ("Projects/main.c",                   3,  kb(8)),
        ("Projects/README.md",                1,  kb(2)),
    ]

    # ------------------------------------------------------------------
    # 3. PROTECTED — game / PrismLauncher / Minecraft / JAR
    #    These should NEVER be touched, even if old.
    # ------------------------------------------------------------------
    protected = [
        # Generic game dir
        ("games/MyGame/assets.pak",                     300, mb(120)),
        ("games/MyGame/save01.sav",                     45,  mb(2)),
        ("games/MyGame/data.bsa",                       400, mb(80)),

        # Top-level mods folder full of jars
        ("mods/jei_1.20.1.jar",                         30,  mb(2)),
        ("mods/optifine_HD.jar",                        200, mb(10)),
        ("mods/create_1.19.2.jar",                      500, mb(15)),

        # PrismLauncher native (~/.local/share/PrismLauncher)
        (".local/share/PrismLauncher/instances/1.20.1-forge/instance.cfg",
                                                        180, kb(2)),
        (".local/share/PrismLauncher/instances/1.20.1-forge/minecraft/mods/sodium.jar",
                                                        400, mb(1)),
        (".local/share/PrismLauncher/instances/1.20.1-forge/minecraft/mods/iris.jar",
                                                        350, mb(2)),
        (".local/share/PrismLauncher/instances/1.20.1-forge/minecraft/saves/World1/level.dat",
                                                        250, kb(50)),
        (".local/share/PrismLauncher/instances/Fabulously-Optimized/minecraft/mods/mod_a.jar",
                                                        90,  mb(3)),

        # PrismLauncher Flatpak location
        (".var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances/Test/minecraft/mods/x.jar",
                                                        300, mb(1)),

        # Plain ~/.minecraft
        (".minecraft/mods/legacy_mod.jar",              600, mb(2)),
        (".minecraft/saves/OldWorld/level.dat",         900, kb(40)),

        # Steam-like
        (".local/share/Steam/steamapps/common/SomeGame/game.pak",
                                                        500, mb(200)),
    ]

    # ------------------------------------------------------------------
    # Create everything
    # ------------------------------------------------------------------
    for rel, days, size in junk:
        p = make_file(root / rel, days, size)
        created.append(("JUNK", p, size))

    for rel, days, size in keepers:
        p = make_file(root / rel, days, size)
        created.append(("KEEP", p, size))

    for rel, days, size in protected:
        p = make_file(root / rel, days, size)
        created.append(("PROTECTED", p, size))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total_junk = sum(1 for c in created if c[0] == "JUNK")
    total_keep = sum(1 for c in created if c[0] == "KEEP")
    total_prot = sum(1 for c in created if c[0] == "PROTECTED")
    total_bytes = sum(c[2] for c in created)

    print()
    print("✅ Sandbox ready.")
    print(f"   Junk files      : {total_junk}")
    print(f"   Keeper files    : {total_keep}")
    print(f"   Protected files : {total_prot}")
    print(f"   Total size      : {total_bytes / (1024*1024):.1f} MB")
    print()
    print("👉 Point the AI cleaner at:")
    print(f"   {root}")
    print()
    print("🧪 Expectation:")
    print("   - Junk files should be flagged by the RL agent.")
    print("   - Keeper files should NOT be flagged.")
    print("   - Protected files (games/PrismLauncher/.jar) must NEVER appear.")
    print()
    print("🧹 To wipe the sandbox later:  rm -rf", root)

# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Generate mock files for AI cleaner testing.")
    ap.add_argument("--path", default=os.path.expanduser("~/ai_cleaner_test"),
                    help="Where to create the sandbox (default: ~/ai_cleaner_test)")
    args = ap.parse_args()
    build_sandbox(Path(args.path).expanduser().resolve())

if __name__ == "__main__":
    main()