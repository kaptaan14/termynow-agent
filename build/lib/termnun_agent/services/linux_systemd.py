from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path


UNIT_NAME = "termnun-agent.service"


def _unit_path() -> Path:
    cfg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return cfg / "systemd" / "user" / UNIT_NAME


def _systemctl(args: list[str]) -> None:
    subprocess.run(["systemctl", "--user", *args], check=True)


def install_user_unit(*, exec_args: list[str], log_file: str) -> None:
    """Install and enable a systemd user service."""
    if shutil.which("systemctl") is None:
        raise RuntimeError("systemctl not found; install systemd user session support.")

    unit_dir = _unit_path().parent
    unit_dir.mkdir(parents=True, exist_ok=True)

    exec_line = " ".join(_shell_quote(a) for a in exec_args)
    env_block = ""
    api = os.environ.get("TERMNU_API_BASE")
    dash = os.environ.get("TERMNU_DASHBOARD_URL")
    lvl = os.environ.get("TERMNU_LOG_LEVEL")
    if api:
        env_block += f"Environment=TERMNU_API_BASE={api}\n"
    if dash:
        env_block += f"Environment=TERMNU_DASHBOARD_URL={dash}\n"
    if lvl:
        env_block += f"Environment=TERMNU_LOG_LEVEL={lvl}\n"
    env_block += f"Environment=TERMNU_LOG_FILE={log_file}\n"
    env_block += "Environment=TERM=xterm-256color\n"

    content = textwrap.dedent(
        f"""\
        [Unit]
        Description=Termnun relay agent
        After=network.target

        [Service]
        Type=simple
        ExecStart={exec_line}
        Restart=always
        RestartSec=3
        {env_block.strip()}

        [Install]
        WantedBy=default.target
        """
    )

    path = _unit_path()
    path.write_text(content + "\n", encoding="utf-8")
    path.chmod(0o644)

    _systemctl(["daemon-reload"])
    _systemctl(["enable", UNIT_NAME])
    _systemctl(["restart", UNIT_NAME])

    try:
        if shutil.which("loginctl"):
            subprocess.run(
                ["loginctl", "enable-linger", os.environ["USER"]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    except Exception:
        pass

    print("✓ Agent installed", flush=True)


def uninstall_user_unit() -> None:
    path = _unit_path()
    if not path.exists():
        return
    try:
        _systemctl(["disable", "--now", UNIT_NAME])
    except subprocess.CalledProcessError:
        pass
    path.unlink(missing_ok=True)
    try:
        _systemctl(["daemon-reload"])
    except subprocess.CalledProcessError:
        pass


def _shell_quote(s: str) -> str:
    if not s:
        return "''"
    if all(c.isalnum() or c in "/._-:=@" for c in s):
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"
