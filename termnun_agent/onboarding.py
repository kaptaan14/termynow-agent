from __future__ import annotations

import logging
import os
import platform

import httpx

from termnun_agent.api_client import ApiError, create_device, delete_device, issue_pairing_code, list_devices, login, mint_agent_token
from termnun_agent.config import AgentConfig

log = logging.getLogger(__name__)


def default_device_name() -> str:
    name = (platform.node() or "").strip() or "termynow-user"
    return name[:128]


def default_dashboard_url() -> str:
    return (os.environ.get("TERMNU_DASHBOARD_URL") or "https://termynow.com").rstrip("/")


async def run_setup(*, api_base: str, email: str, password: str, device_name: str | None = None) -> None:
    """Login, register this machine (reuse pending same hostname when possible), mint pairing OTP, persist config."""
    name = (device_name or default_device_name()).strip() or default_device_name()
    api_base = api_base.rstrip("/")

    print("Logging in...", flush=True)
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            token = await login(client, api_base, email, password)
        except ApiError as e:
            log.error("%s", e)
            raise SystemExit(2) from e

        print("Registering device...", flush=True)
        try:
            devices = await list_devices(client, api_base, token)
            pending_same = [
                d
                for d in devices
                if str(d.get("verify_status") or "") == "pending" and str(d.get("name") or "") == name
            ]
            if pending_same:
                primary = pending_same[0]
                device_id = str(primary["id"])
                log.info("reusing pending device id=%s name=%r", device_id, name)
                print(f"Reusing existing pending device ({name})…", flush=True)
                for dup in pending_same[1:]:
                    did = str(dup["id"])
                    log.info("removing duplicate pending device id=%s", did)
                    try:
                        await delete_device(client, api_base, token, did)
                    except ApiError as e:
                        log.warning("could not delete duplicate device %s: %s", did, e)
            else:
                created = await create_device(client, api_base, token, name)
                device_id = str(created["id"])
        except ApiError as e:
            log.error("%s", e)
            raise SystemExit(2) from e

        print("Generating pairing code...", flush=True)
        try:
            pair = await issue_pairing_code(client, api_base, token, device_id)
        except ApiError as e:
            log.error("%s", e)
            raise SystemExit(2) from e

        # try:
        #     agent = await mint_agent_token(client, api_base, token, device_id)
        # except ApiError as e:
        #     log.error("%s", e)
        #     raise SystemExit(2) from e

    cfg = AgentConfig(api_base=api_base, access_token=token, device_id=device_id)
    cfg.save()

    code = str(pair["code"])
    expires = int(pair.get("expires_in_seconds") or 0)
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
