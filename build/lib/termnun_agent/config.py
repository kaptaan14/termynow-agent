from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "termynow"
    return Path.home() / ".config" / "termynow"


@dataclass
class AgentConfig:
    api_base: str
    access_token: str | None = None
    device_id: str | None = None
    agent_token: str | None = None

    @staticmethod
    def paths() -> tuple[Path, Path]:
        d = _config_dir()
        d.mkdir(parents=True, exist_ok=True)
        return d / "state.json", d / "agent.env"

    def save(self) -> None:
        path, _ = self.paths()
        data = {
            "api_base": self.api_base.rstrip("/"),
            "access_token": self.access_token,
            "device_id": self.device_id,
            "agent_token": self.agent_token
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    @classmethod
    def load(cls) -> AgentConfig | None:
        path, _ = cls.paths()
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            api_base=str(raw.get("api_base") or "").rstrip("/"),
            access_token=raw.get("access_token"),
            device_id=raw.get("device_id"),
            agent_token=raw.get("agent_token")
        )
