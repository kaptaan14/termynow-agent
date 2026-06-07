from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path


LABEL = "dev.termynow.agent"
PLIST_NAME = f"{LABEL}.plist"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / PLIST_NAME


def install_agent(*, exec_args: list[str], log_file: str) -> None:
    if shutil.which("launchctl") is None:
        raise RuntimeError("launchctl not found.")

    out_dir = Path.home() / "Library" / "LaunchAgents"
    out_dir.mkdir(parents=True, exist_ok=True)

    env: dict[str, str] = {"TERMYNOW_LOG_FILE": log_file}
    mapping = {
        "TERMYNOW_API_BASE": "TERMNU_API_BASE",
        "TERMYNOW_DASHBOARD_URL": "TERMNU_DASHBOARD_URL",
        "TERMYNOW_LOG_LEVEL": "TERMNU_LOG_LEVEL",
    }
    for key, fallback in mapping.items():
        val = os.environ.get(key) or os.environ.get(fallback)
        if val:
            env[key] = val

    plist: dict = {
        "Label": LABEL,
        "ProgramArguments": exec_args,
        "RunAtLoad": True,
        "KeepAlive": True,
        "EnvironmentVariables": env,
        "StandardOutPath": log_file,
        "StandardErrorPath": log_file,
    }

    path = _plist_path()
    path.write_bytes(plistlib.dumps(plist, fmt=plistlib.FMT_XML))
    path.chmod(0o644)

    # Best-effort unload then load (works across macOS versions).
    subprocess.run(["launchctl", "unload", str(path)], check=False, capture_output=True)
    subprocess.run(["launchctl", "load", "-w", str(path)], check=True)

    print("✓ Agent installed", flush=True)
    print("✓ Background service enabled (LaunchAgent)", flush=True)
    print("✓ Persistent reconnect enabled", flush=True)


def uninstall_agent() -> None:
    path = _plist_path()
    if not path.exists():
        return
    subprocess.run(["launchctl", "unload", str(path)], check=False, capture_output=True)
    path.unlink(missing_ok=True)
