from __future__ import annotations

import logging
import os
import platform

import httpx

from termnun_agent.api_client import ApiError, register_device_anonymous
from termnun_agent.config import AgentConfig

log = logging.getLogger(__name__)


def default_device_name() -> str:
    name = (platform.node() or "").strip() or "termynow-user"
    return name[:128]


def default_dashboard_url() -> str:
    return (os.environ.get("TERMYNOW_DASHBOARD_URL") or os.environ.get("TERMNU_DASHBOARD_URL") or "https://termynow.com").rstrip("/")


async def run_setup(*, api_base: str, device_name: str | None = None) -> None:
    """Register this machine anonymously, get device credentials and pairing OTP, persist config."""
    name = (device_name or default_device_name()).strip() or default_device_name()
    api_base = api_base.rstrip("/")

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            reg = await register_device_anonymous(client, api_base, name)
        except ApiError as e:
            log.error("%s", e)
            raise SystemExit(2) from e

    device_id = str(reg["device_id"])
    token = str(reg["access_token"])
    code = str(reg["code"])
    expires = int(reg.get("expires_in_seconds") or 0)

    cfg = AgentConfig(api_base=api_base, access_token=token, device_id=device_id)
    cfg.save()

    dash = default_dashboard_url()

    print("", flush=True)
    print("Your pairing code:", flush=True)
    print(code, flush=True)
    print("", flush=True)
    print(f"Open {dash} and enter this code to complete pairing.", flush=True)
    if expires:
        print(f"(Code expires in {expires} seconds.)", flush=True)
    print("", flush=True)
    print("After pairing, the agent will connect automatically.", flush=True)
