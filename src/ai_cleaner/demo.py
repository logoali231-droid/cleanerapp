"""Generates a sandbox of realistic fake files for testing."""
import os
from pathlib import Path
from datetime import datetime, timedelta


def create_demo_files(root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    def mk(rel, days, size):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            chunk = b"\x42" * 8192
            w = 0
            while w < size:
                n = min(len(chunk), size - w)
                f.write(chunk[:n])
                w += n
        ts = (datetime.now() - timedelta(days=days)).timestamp()
        os.utime(p, (ts, ts))

    junk = [
        ("tmp/setup_legacy_tool.deb", 220, 15 * 1048576),
        ("tmp/old_package_manager.rpm", 310, 8 * 1048576),
        ("tmp/NodeApp-3.2.1.AppImage", 160, 45 * 1048576),
        ("tmp/gpu_driver_installer.run", 400, 120 * 1048576),
        ("tmp/build_debug.log", 65, 800 * 1024),
        ("tmp/core.dump", 75, 300 * 1048576),
        ("var/tmp/cache_build.tar.gz", 180, 20 * 1048576),
        ("Downloads/ubuntu_iso_2022.iso", 500, 700 * 1048576),
        ("Downloads/photos_backup.zip", 240, 80 * 1048576),
        ("Downloads/random_article.tar.xz", 190, 12 * 1048576),
        ("Downloads/video_rip_old.mp4", 380, 250 * 1048576),
        ("cache/thumbs_cache.dat", 95, 30 * 1048576),
        ("cache/browser_cache.bin", 130, 60 * 1048576),
        ("cache/stale_index.tmp", 400, 400 * 1024),
    ]
    keepers = [
        ("Documents/thesis_final.pdf", 5, 2 * 1048576),
        ("Documents/notes.txt", 2, 30 * 1024),
        ("Pictures/vacation_2024.jpg", 8, 4 * 1048576),
        ("Projects/myscript.py", 1, 15 * 1024),
        ("Projects/main.c", 3, 8 * 1024),
    ]
    protected = [
        ("games/MyGame/assets.pak", 300, 120 * 1048576),
        ("mods/jei_1.20.1.jar", 30, 2 * 1048576),
        (".local/share/PrismLauncher/instances/1.20.1-forge/minecraft/mods/sodium.jar",
         400, 1048576),
        (".minecraft/mods/legacy_mod.jar", 600, 2 * 1048576),
    ]

    for rel, d, s in junk + keepers + protected:
        mk(rel, d, s)

    return {
        "junk": len(junk),
        "keepers": len(keepers),
        "protected": len(protected),
        "path": str(root),
        "total_mb": sum(s for _, _, s in junk + keepers + protected) / 1048576,
    }