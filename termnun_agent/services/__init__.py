from __future__ import annotations

import sys

from termnun_agent.services import linux_systemd, macos_launchd, windows_stub


def install_background_service(*, foreground_exec: list[str], log_file: str) -> None:
    if sys.platform == "linux":
        linux_systemd.install_user_unit(exec_args=foreground_exec, log_file=log_file)
        return
    if sys.platform == "darwin":
        macos_launchd.install_agent(exec_args=foreground_exec, log_file=log_file)
        return
    windows_stub.raise_install_unsupported()


def uninstall_background_service() -> None:
    if sys.platform == "linux":
        linux_systemd.uninstall_user_unit()
        return
    if sys.platform == "darwin":
        macos_launchd.uninstall_agent()
        return
    windows_stub.print_windows_notice()
