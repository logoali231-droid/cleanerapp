"""Admin relaunch: terminal / pkexec / askpass."""
import os
import sys
import shutil
import shlex
import tempfile
import subprocess
from datetime import datetime

from .config import HOME, CONFIG_DIR


def _admin_log(msg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(os.path.join(CONFIG_DIR, "admin-launch.log"), "a") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    except Exception:
        pass


def find_terminal():
    for t in ("mate-terminal", "x-terminal-emulator", "gnome-terminal",
              "xfce4-terminal", "konsole", "kitty", "alacritty", "xterm"):
        p = shutil.which(t)
        if p:
            return p
    return None


def find_askpass():
    for tool in ("zenity", "yad", "ssh-askpass", "ssh-askpass-gnome",
                 "ksshaskpass", "lxqt-openssh-askpass"):
        p = shutil.which(tool)
        if p:
            return p
    return None


def _build_script_launcher(tmp_script, python, script, folder, deep):
    lines = [
        "#!/bin/bash",
        "echo '=== AI File Cleaner — admin launch ==='",
        "echo 'The system will now ask for your password.'",
        "echo",
    ]
    cmd = f"sudo -E {shlex.quote(python)} {shlex.quote(script)} --admin"
    if folder: cmd += f" --folder {shlex.quote(folder)}"
    if deep:   cmd += " --deep"
    lines.append(cmd)
    lines += [
        "rc=$?",
        "echo",
        "if [ $rc -ne 0 ]; then echo \"=== Launch failed (exit $rc) ===\"; fi",
        "echo 'Press Enter to close this window…'",
        "read _",
        f"rm -f {shlex.quote(tmp_script)}",
    ]
    return "\n".join(lines) + "\n"


def terminal_argv(term, script_path):
    name = os.path.basename(term)
    if name in ("gnome-terminal", "mate-terminal"):
        return [term, "--", "bash", script_path]
    if name == "xfce4-terminal":
        return [term, "--command", f"bash {shlex.quote(script_path)}"]
    if name == "konsole":
        return [term, "-e", "bash", script_path]
    return [term, "-e", "bash", script_path]


def relaunch_as_admin(folder=None, deep=False, method="terminal",
                      signal_file=None, parent=None):
    python = sys.executable or "python3"
    # __main__.py is our entry point — invoke the package as a module
    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    inner = [python, "-m", "ai_cleaner", "--admin"]
    if folder:      inner += ["--folder", folder]
    if deep:        inner += ["--deep"]
    if signal_file: inner += ["--signal-file", signal_file]

    _admin_log(f"method={method}  folder={folder}  deep={deep}")
    _admin_log(f"python={python}")
    _admin_log(f"package_dir={package_dir}")
    _admin_log(f"signal={signal_file}")

    if method == "terminal":
        term = find_terminal()
        if not term:
            return False, ("Couldn't find a terminal emulator.\n\n"
                           "Install one with:  sudo apt install mate-terminal")
        fd, tmp = tempfile.mkstemp(prefix="ai-cleaner-launch-", suffix=".sh")
        os.close(fd)
        try:
            with open(tmp, "w") as f:
                f.write(_build_script_launcher(tmp, python, package_dir, folder, deep))
            os.chmod(tmp, 0o755)
            # shell wrapper: cd into the parent and set PYTHONPATH
            script = f"""#!/bin/bash
cd {shlex.quote(package_dir)}
export PYTHONPATH={shlex.quote(package_dir)}:$PYTHONPATH
export AI_CLEANER_USER_HOME={shlex.quote(HOME)}
sudo -E {shlex.quote(python)} -m ai_cleaner --admin""" + (
                f" --folder {shlex.quote(folder)}" if folder else ""
            ) + (" --deep" if deep else "") + (
                f" --signal-file {shlex.quote(signal_file)}" if signal_file else ""
            ) + """
"""
            with open(tmp, "w") as f:
                f.write(script)
            os.chmod(tmp, 0o755)
            argv = terminal_argv(term, tmp)
            _admin_log(f"exec: {argv}")
            subprocess.Popen(argv, close_fds=True)
            return True, ""
        except Exception as e:
            _admin_log(f"terminal Popen failed: {e}")
            return False, f"Couldn't launch {term}:\n\n{e}"

    if method == "askpass":
        askpass = find_askpass()
        if not askpass:
            return False, ("No graphical password tool found.\n\n"
                           "Install one with:  sudo apt install zenity\n"
                           "Or switch to Terminal.")
        env = os.environ.copy()
        env["SUDO_ASKPASS"] = askpass
        env["AI_CLEANER_USER_HOME"] = HOME
        env["PYTHONPATH"] = package_dir + os.pathsep + env.get("PYTHONPATH", "")
        try:
            _admin_log(f"askpass={askpass}")
            subprocess.Popen(["sudo", "-A", "-E"] + inner,
                             env=env, cwd=package_dir, close_fds=True)
            return True, ""
        except Exception as e:
            _admin_log(f"askpass failed: {e}")
            return False, f"Couldn't launch sudo with {askpass}:\n\n{e}"

    if method == "pkexec":
        pkexec = shutil.which("pkexec")
        if not pkexec:
            return False, ("pkexec isn't installed.\n\n"
                           "Switch the method to 'Terminal' and try again.")
        env_pairs = [
            f"HOME={os.environ.get('HOME','')}",
            f"DISPLAY={os.environ.get('DISPLAY', ':0')}",
            f"XAUTHORITY={os.environ.get('XAUTHORITY', os.path.expanduser('~/.Xauthority'))}",
            f"XDG_RUNTIME_DIR={os.environ.get('XDG_RUNTIME_DIR','')}",
            f"AI_CLEANER_USER_HOME={HOME}",
            f"PYTHONPATH={package_dir}",
            "QT_QPA_PLATFORM=xcb",
        ]
        argv = [pkexec, "env", "-C", package_dir] + env_pairs + inner
        try:
            _admin_log(f"exec: {argv}")
            subprocess.Popen(argv, close_fds=True)
            return True, ""
        except Exception as e:
            _admin_log(f"pkexec failed: {e}")
            return False, f"Couldn't launch pkexec:\n\n{e}"

    return False, f"Unknown method: {method}"