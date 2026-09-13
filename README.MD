# AI File Cleaner

A Linux file cleaner with a small reinforcement-learning agent. Finds unused
files and installation leftovers, protects your games and dev work, and learns
from your keep/delete decisions.

## Features

- RL-based decisions (tabular Q-learning) with dynamic confidence
- Rule system — teach it once, it remembers
- Trash-safe deletion — restore from Nemo
- Protects Steam, Lutris, PrismLauncher, Minecraft, `.jar`, `/usr`, `/etc`
- Screenshot detection with configurable age
- Runs entirely on your machine. No network, no cloud.

## Install (Flatpak)

    flatpak run --command=flathub-build org.flatpak.Builder \
        --install com.dipper.AIFileCleaner.json

## Install (from source)

    git clone https://github.com/logoali231-droid/cleanerapp
    cd cleanerapp && ./setup.sh

## License

GPL-3.0-or-later