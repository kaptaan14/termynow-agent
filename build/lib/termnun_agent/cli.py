from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import shutil
import sys

import httpx

from termnun_agent.api_client import ApiError, create_device, issue_pairing_code, login
from termnun_agent.client import RelayClient
from termnun_agent.config import AgentConfig
from termnun_agent.logging_config import default_log_path, setup_logging
from termnun_agent.onboarding import default_device_name, run_setup
from termnun_agent.services import install_background_service, uninstall_background_service

log = logging.getLogger(__name__)


def _default_api_base() -> str:
    return (os.environ.get("TERMYNOW_API_BASE") or os.environ.get("TERMNU_API_BASE") or "https://termynow.com").rstrip("/")


async def _cmd_login(email: str, password: str, api_base: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            tok = await login(client, api_base, email, password)
    except ApiError as e:
        log.error("%s", e)
        raise SystemExit(2) from e
    cfg = AgentConfig.load()
    if cfg is None:
        cfg = AgentConfig(api_base=api_base, access_token=tok)
    else:
        cfg.api_base = api_base
        cfg.access_token = tok
        cfg.agent_token = tok
    cfg.save()
    log.info("saved credentials to %s", AgentConfig.paths()[0])


async def _cmd_device_create(api_base: str, token: str, name: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        data = await create_device(client, api_base, token, name)
    log.info("device id=%s (status=%s)", data["id"], data["verify_status"])
    cfg = AgentConfig.load() or AgentConfig(api_base=api_base)
    cfg.api_base = api_base
    cfg.access_token = token
    cfg.device_id = str(data["id"])
    cfg.save()


async def _cmd_pairing_code(api_base: str, token: str, device_id: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        data = await issue_pairing_code(client, api_base, token, device_id)
    log.info("OTP (enter in web dashboard): %s  (expires in %ss)", data["code"], data["expires_in_seconds"])


def _prompt_credentials(email: str | None, password: str | None) -> tuple[str, str]:
    e = email or os.environ.get("TERMYNOW_EMAIL") or os.environ.get("TERMNU_EMAIL") or ""
    p = password or os.environ.get("TERMYNOW_PASSWORD") or os.environ.get("TERMNU_PASSWORD") or ""
    if not e and sys.stdin.isatty():
        e = input("Email: ").strip()
    if not p and sys.stdin.isatty():
        p = getpass.getpass("Password: ")
    if not e or not p:
        log.error("email and password are required (flags, environment, or TTY prompts)")
        raise SystemExit(2)
    return e, p


def main() -> None:
    p = argparse.ArgumentParser(prog="termynow-agent", description="Termynow laptop relay agent")
    p.add_argument("--api-base", default=_default_api_base(), help="API base URL (or TERMNU_API_BASE)")

    subs = p.add_subparsers(dest="cmd")

    setup = subs.add_parser("setup", help="one-step anonymous device registration and pairing code")
    setup.add_argument("--device-name", default=None, help="override auto-detected device name")

    inst = subs.add_parser("install-service", help="install OS background service (systemd / launchd)")
    inst.add_argument(
        "--no-start",
        action="store_true",
        help="reserved for future use (service is always enabled and started)",
    )

    un = subs.add_parser("uninstall-service", help="remove OS background service")

    run = subs.add_parser("run", help="run relay client (use under systemd/LaunchAgent with --foreground)")
    run.add_argument("--foreground", action="store_true", help="stay attached; log to stderr and file")
    run.add_argument("--log-level", default=None)

    lg = subs.add_parser("login", help="store user JWT credentials only")
    lg.add_argument("--email", required=True)
    lg.add_argument("--password", required=True)

    dc = subs.add_parser("device-create", help="register laptop device under your account")
    dc.add_argument("--name", default=None, help="defaults to this machine's hostname")

    pc = subs.add_parser("pairing-code", help="print OTP to confirm pairing from the web dashboard")
    pc.add_argument("--device-id")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        raise SystemExit(1)

    api_base = str(args.api_base).rstrip("/")

    if args.cmd == "run":
        setup_logging(level=args.log_level, foreground=args.foreground)
        cfg = AgentConfig.load()
        if cfg is None or not cfg.access_token or not cfg.device_id:
            log.error("missing config; run `termynow-agent setup` first")
            raise SystemExit(2)
        client = RelayClient(cfg)
        asyncio.run(client.run_forever())
        return

    if args.cmd == "setup":
        setup_logging(level=os.environ.get("TERMYNOW_LOG_LEVEL") or os.environ.get("TERMNU_LOG_LEVEL"), foreground=True)
        name = args.device_name or default_device_name()
        asyncio.run(run_setup(api_base=api_base, device_name=name))
        return

    if args.cmd == "install-service":
        setup_logging(level=os.environ.get("TERMYNOW_LOG_LEVEL") or os.environ.get("TERMNU_LOG_LEVEL"), foreground=True)
        exe = shutil.which("termynow-agent")
        if not exe:
            log.error("termynow-agent executable not found on PATH")
            raise SystemExit(2)
        log_path = str(default_log_path())
        exec_args = [exe, "run", "--foreground"]
        if getattr(args, "no_start", False):
            log.warning("--no-start is ignored; service is always enabled and started")
        install_background_service(foreground_exec=exec_args, log_file=log_path)
        return

    if args.cmd == "uninstall-service":
        setup_logging(foreground=True)
        uninstall_background_service()
        return

    setup_logging(level=os.environ.get("TERMYNOW_LOG_LEVEL") or os.environ.get("TERMNU_LOG_LEVEL"), foreground=True)

    async def runner() -> None:
        if args.cmd == "login":
            await _cmd_login(args.email, args.password, api_base)
            return
        cfg = AgentConfig.load()
        if cfg is None or not cfg.access_token:
            log.error("run `termynow-agent login` or `termynow-agent setup` first")
            raise SystemExit(2)
        if args.cmd == "device-create":
            nm = args.name or default_device_name()
            try:
                await _cmd_device_create(cfg.api_base, cfg.access_token, nm)
            except ApiError as e:
                log.error("%s", e)
                raise SystemExit(2) from e
            return
        if args.cmd == "pairing-code":
            device_id = args.device_id or cfg.device_id
            if not device_id:
                log.error("no device-id; create a device first")
                raise SystemExit(2)
            try:
                await _cmd_pairing_code(cfg.api_base, cfg.access_token, device_id)
            except ApiError as e:
                log.error("%s", e)
                raise SystemExit(2) from e
            return

    asyncio.run(runner())


if __name__ == "__main__":
    main()
