from __future__ import annotations


def raise_install_unsupported() -> None:
    print(
        "Windows native service installation is not available yet.\n"
        "Run the agent in the background with:\n"
        "  termnun-agent run --foreground\n"
        "or schedule a Task Scheduler job that invokes the same command.",
        flush=True,
    )
    raise SystemExit(2)


def print_windows_notice() -> None:
    """Reserved for uninstall flows that should be non-fatal on Windows."""
    print("Windows: no LaunchAgent/systemd unit to remove.", flush=True)
