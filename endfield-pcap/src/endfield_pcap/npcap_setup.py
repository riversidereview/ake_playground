from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys

from .npcap import has_npcap
from .runtime_paths import app_root, bundle_root

LOGGER = logging.getLogger(__name__)


def find_bundled_npcap_installer() -> Path | None:
    """Locate bundled Npcap installer (e.g. npcap-1.88.exe, npcap-installer.exe)."""
    search_dirs = [
        app_root(),
        app_root().parent if app_root() else None,
        bundle_root(),
        bundle_root().parent if bundle_root() else None,
        Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd(),
        app_root() / "installer",
        bundle_root() / "installer",
    ]
    seen_dirs: set[Path] = set()
    for directory in search_dirs:
        if directory is None:
            continue
        try:
            resolved = directory.resolve()
        except OSError:
            resolved = directory
        if resolved in seen_dirs or not resolved.exists():
            continue
        seen_dirs.add(resolved)

        # Look for specific pattern matches first
        for pattern in ("npcap-1.88.exe", "npcap-*.exe", "npcap-installer.exe", "npcap.exe"):
            for match in resolved.glob(pattern):
                if match.is_file():
                    return match.resolve()
    return None


def launch_npcap_installer(installer_path: Path) -> bool:
    """Launch the Npcap installer with UAC elevation on Windows."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes

        # Use ShellExecuteW 'runas' to ensure administrator elevation prompt
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            str(installer_path),
            None,
            str(installer_path.parent),
            1,  # SW_SHOWNORMAL
        )
        # ShellExecute returns > 32 on success
        return int(result) > 32
    except Exception:
        LOGGER.warning("failed to launch Npcap installer via ShellExecute", exc_info=True)
        try:
            subprocess.Popen([str(installer_path)], cwd=str(installer_path.parent))
            return True
        except OSError:
            LOGGER.error("failed to launch Npcap installer via subprocess", exc_info=True)
            return False


def prompt_npcap_install_interactive() -> bool:
    """Check Npcap and interactively prompt user if missing."""
    if has_npcap():
        return True

    installer = find_bundled_npcap_installer()

    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass

        if installer is not None:
            title = "Npcap Driver Setup Required"
            message = (
                "Npcap packet capture driver was not detected on your system.\n\n"
                "Npcap is required for real-time combat data capturing and DPS overlay.\n\n"
                f"Bundled installer found: {installer.name}\n\n"
                "Would you like to install Npcap now?\n\n"
                "• Click 'Yes' to launch the Npcap installer.\n"
                "• Click 'No' to continue in Offline Log Analysis & Upload mode."
            )
            install_choice = messagebox.askyesno(title, message, parent=root)
            if install_choice:
                launched = launch_npcap_installer(installer)
                if launched:
                    messagebox.showinfo(
                        "Npcap Installation Started",
                        "The Npcap installer has been launched.\n\n"
                        "Please complete the installation wizard.\n"
                        "(Tip: If prompted, keep 'WinPcap API-compatible Mode' enabled).\n\n"
                        "After installation completes, please restart Endfield Logs Client for live capture.\n\n"
                        "Click OK to exit.",
                        parent=root,
                    )
                else:
                    messagebox.showwarning(
                        "Installer Launch Failed",
                        f"Failed to launch {installer.name}.\n\n"
                        f"Please manually run the installer located at:\n{installer}\n\n"
                        "Exiting client.",
                        parent=root,
                    )
                return False
            else:
                messagebox.showinfo(
                    "Offline Mode Enabled",
                    "Npcap installation was skipped.\n\n"
                    "Real-time packet capture is disabled, but you can still use offline log analysis, "
                    "replays, and combat log uploading.",
                    parent=root,
                )
                return True
        else:
            title = "Npcap Driver Not Found"
            message = (
                "Npcap driver was not detected on your system and no local installer was found.\n\n"
                "Real-time packet capture will be disabled.\n\n"
                "To enable real-time capture later, download and install Npcap from:\n"
                "https://npcap.com/#download\n\n"
                "Continuing in Offline Log Analysis & Upload mode."
            )
            messagebox.showinfo(title, message, parent=root)
            return True
    finally:
        root.destroy()
