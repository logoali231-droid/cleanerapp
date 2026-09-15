"""PyInstaller entry point for the Windows build.

This file intentionally uses absolute imports. PyInstaller executes its
entry-point script as ``__main__``, so package-relative imports from
``ai_cleaner.__main__`` would fail with ``no known parent package``.
"""
from ai_cleaner.ui.wizard import Wizard, main
from ai_cleaner.ui.windows_compat import install_windows_compat

install_windows_compat(Wizard)

if __name__ == "__main__":
    main()
