"""Entry point: `python3 -m ai_cleaner`."""
from .ui.wizard import Wizard, main
from .ui.windows_compat import install_windows_compat
from .ui.windows_ui_text import install_windows_ui_text

install_windows_compat(Wizard)
install_windows_ui_text(Wizard)

if __name__ == "__main__":
    main()
