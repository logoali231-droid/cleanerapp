"""Entry point: `python3 -m ai_cleaner`."""
from .ui.wizard import Wizard, main
from .ui.windows_compat import install_windows_compat

install_windows_compat(Wizard)

if __name__ == "__main__":
    main()
