from __future__ import annotations

from typing import Any

import httpx


class ApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def login(client: httpx.AsyncClient, api_base: str, email: str, password: str) -> str:
    r = await client.post(f"{api_base}/v1/auth/login", json={"email": email, "password": password})
    if r.status_code >= 400:
        raise ApiError(f"login failed: {r.text}", status_code=r.status_code)
    return str(r.json()["access_token"])


async def list_devices(client: httpx.AsyncClient, api_base: str, token: str) -> list[dict[str, Any]]:
    r = await client.get(f"{api_base}/v1/devices", headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        raise ApiError(f"list devices failed: {r.text}", status_code=r.status_code)
    data = r.json()
    return data if isinstance(data, list) else []


async def delete_device(client: httpx.AsyncClient, api_base: str, token: str, device_id: str) -> None:
    r = await client.delete(
        f"{api_base}/v1/devices/{device_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code >= 400:
        raise ApiError(f"delete device failed: {r.text}", status_code=r.status_code)


async def create_device(client: httpx.AsyncClient, api_base: str, token: str, name: str) -> dict[str, Any]:
    r = await client.post(
        f"{api_base}/v1/devices",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code >= 400:
        raise ApiError(f"device registration failed: {r.text}", status_code=r.status_code)
    return r.json()


async def issue_pairing_code(client: httpx.AsyncClient, api_base: str, token: str, device_id: str) -> dict[str, Any]:
    r = await client.post(
        f"{api_base}/v1/devices/{device_id}/pairing-code",
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code >= 400:
        raise ApiError(f"pairing code failed: {r.text}", status_code=r.status_code)
    return r.json()


async def mint_agent_token(client: httpx.AsyncClient, api_base: str, token: str, device_id: str) -> dict[str, Any]:
    r = await client.post(
        f"{api_base}/v1/devices/{device_id}/agent-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code >= 400:
        raise ApiError(f"pairing code failed: {r.text}", status_code=r.status_code)
    return r.json()


async def register_device_anonymous(client: httpx.AsyncClient, api_base: str, name: str) -> dict[str, Any]:
    r = await client.post(
        f"{api_base}/v1/devices/register-anonymous",
        json={"name": name},
    )
    if r.status_code >= 400:
        raise ApiError(f"Device registration failed: {r.text}", status_code=r.status_code)
    return r.json()
