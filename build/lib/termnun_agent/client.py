from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from termnun_agent.config import AgentConfig
from termnun_agent.fs_ops import dispatch_file_message
from termnun_agent.pty_session import PtySession
from termnun_agent.reconnect import Backoff

log = logging.getLogger(__name__)

RESULT_FOR = {
    "file.list": "file.list_result",
    "file.read_begin": "file.read_progress",
    "file.read_next": "file.read_progress",
    "file.write_begin": "file.write_ack",
    "file.write_chunk": "file.write_ack",
    "proc.list": "proc.list_result",
    "sys.stats": "sys.stats_result",
}


class RelayClient:
    def __init__(self, cfg: AgentConfig) -> None:
        self.cfg = cfg
        self.ws: object | None = None
        self.sessions: dict[str, PtySession] = {}

    async def _emit_terminal(self, session_id: str, data: bytes) -> None:
        if self.ws is None:
            return
        payload = {"chunk": base64.b64encode(data).decode("ascii")}
        env = {"type": "terminal.output", "session_id": session_id, "payload": payload}
        await self.ws.send(json.dumps(env))

    async def _handle(self, raw: str) -> None:
        try:
            msg: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            return
        t = str(msg.get("type") or "")
        sid = msg.get("session_id")
        sid_str = str(sid) if sid is not None else None
        if t == "session.open" and sid_str:
            payload = msg.get("payload") or {}
            cols = int(payload.get("cols") or 120)
            rows = int(payload.get("rows") or 36)
            if sid_str in self.sessions:
                await self.sessions[sid_str].close()
                del self.sessions[sid_str]

            async def on_out(data: bytes) -> None:
                await self._emit_terminal(sid_str, data)

            sess = PtySession(sid_str, cols, rows, on_out)
            sess.spawn()
            self.sessions[sid_str] = sess
            return
        if t == "terminal.input" and sid_str and sid_str in self.sessions:
            chunk = (msg.get("payload") or {}).get("chunk")
            if chunk:
                self.sessions[sid_str].write(base64.b64decode(str(chunk)))
            return
        if t == "terminal.resize" and sid_str and sid_str in self.sessions:
            payload = msg.get("payload") or {}
            cols = int(payload.get("cols") or 120)
            rows = int(payload.get("rows") or 36)
            self.sessions[sid_str].resize(cols, rows)
            return
        if t == "session.close" and sid_str and sid_str in self.sessions:
            await self.sessions[sid_str].close()
            del self.sessions[sid_str]
            return

        if t in RESULT_FOR and self.ws is not None:
            res = dispatch_file_message(msg)
            if res is None:
                return
            out = {"type": RESULT_FOR[t], "session_id": sid_str, "payload": res}
            await self.ws.send(json.dumps(out))

    async def _shutdown_local_sessions(self) -> None:
        for sid in list(self.sessions.keys()):
            await self._handle(json.dumps({"type": "session.close", "session_id": sid}))

    async def _mint_agent_token(self) -> str:
        assert self.cfg.device_id and self.cfg.access_token
        url = f"{self.cfg.api_base}/v1/devices/{self.cfg.device_id}/agent-token"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                url,
                headers={"Authorization": f"Bearer {self.cfg.access_token}"},
            )
            r.raise_for_status()
            return str(r.json()["access_token"])

    async def _run_connected_session(self, backoff: Backoff) -> None:
        token = await self._mint_agent_token()
        ws_base = self.cfg.api_base.replace("http://", "ws://").replace("https://", "wss://")
        uri = f"{ws_base}/ws/agent?token={token}"
        async with websockets.connect(uri, ping_interval=20, ping_timeout=120) as ws:
            self.ws = ws
            backoff.reset()
            log.info("connected to relay; sessions will attach when the dashboard opens a terminal")
            async for message in ws:
                if isinstance(message, bytes):
                    continue
                await self._handle(message)

    async def run_forever(self) -> None:
        """
        Infinite reconnect loop: mint token, connect WebSocket, process messages,
        then tear down local PTYs and backoff before retrying.
        """
        backoff = Backoff(initial=1.0, max_seconds=60.0, multiplier=2.0, min_seconds=1.0)
        while True:
            delay: float | None = None
            try:
                await self._run_connected_session(backoff)
                log.info("relay session ended; will reconnect")
            except ConnectionClosed as e:
                log.warning(
                    "relay disconnected (code=%s reason=%s); reconnecting with backoff",
                    getattr(e, "code", None),
                    getattr(e, "reason", None),
                )
            except httpx.HTTPStatusError as e:
                if e.response is not None and e.response.status_code == 403:
                    log.warning(
                        "Device not verified yet (enter pairing code in the dashboard). "
                        "Retrying in %.1fs",
                        backoff.peek_cap(),
                    )
                else:
                    log.error("failed to mint agent token (HTTP %s): %s", e.response.status_code if e.response else "?", e)
            except httpx.RequestError as e:
                log.warning("API or network error: %s", e)
            except OSError as e:
                log.warning("OS network error: %s", e)
            except Exception:
                log.exception("unexpected relay error")
            finally:
                self.ws = None
                await self._shutdown_local_sessions()
                self.sessions.clear()

            delay = backoff.next_delay()
            log.info("reconnecting in %.1fs", delay)
            await asyncio.sleep(delay)
