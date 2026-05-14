from __future__ import annotations

import base64
import os
from pathlib import Path


def _safe_resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.home() / p
    try:
        resolved = p.resolve()
    except OSError as e:
        raise ValueError(str(e)) from e
    return resolved


def list_dir(path: str) -> list[dict]:
    root = _safe_resolve(path)
    if not root.exists():
        return []
    if not root.is_dir():
        return []
    items: list[dict] = []
    for child in sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        try:
            st = child.stat()
            items.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "is_dir": child.is_dir(),
                    "size": st.st_size if child.is_file() else 0,
                    "mtime": int(st.st_mtime),
                }
            )
        except OSError:
            continue
    return items


def read_file_b64(path: str, offset: int, length: int) -> tuple[bytes, bool]:
    resolved = _safe_resolve(path)
    if not resolved.is_file():
        raise FileNotFoundError(path)
    with resolved.open("rb") as f:
        f.seek(offset)
        data = f.read(length)
    next_offset = offset + len(data)
    more = next_offset < resolved.stat().st_size
    return data, more


def write_file_begin(path: str) -> None:
    resolved = _safe_resolve(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_bytes(b"")


def write_file_chunk(path: str, chunk_b64: str, append: bool) -> None:
    resolved = _safe_resolve(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    data = base64.b64decode(chunk_b64)
    mode = "ab" if append else "wb"
    if not append and os.path.exists(resolved):
        resolved.unlink()
    with resolved.open(mode) as f:
        f.write(data)


def proc_snapshot() -> dict:
    pids: list[dict] = []
    for name in sorted(os.listdir("/proc")):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="ignore") as f:
                stat = f.read()
            parts = stat.rsplit(")", 1)
            if len(parts) != 2:
                continue
            comm = parts[0].split("(", 1)[1]
            rest = parts[1].split()
            state = rest[0]
            utime = int(rest[11])
            stime = int(rest[12])
            rss_pages = int(rest[21])
            pids.append(
                {
                    "pid": pid,
                    "name": comm[:64],
                    "state": state,
                    "cpu_ticks": utime + stime,
                    "rss_kb": rss_pages * (os.sysconf("SC_PAGE_SIZE") // 1024),
                }
            )
        except (OSError, ValueError, IndexError):
            continue
    pids.sort(key=lambda x: x["cpu_ticks"], reverse=True)
    return {"processes": pids[:200]}


def sys_stats() -> dict:
    load = "0 0 0"
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as f:
            load = f.read().split()[0:3]
            load = " ".join(load)
    except OSError:
        pass
    mem_total = mem_avail = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])  # kB
                elif line.startswith("MemAvailable:"):
                    mem_avail = int(line.split()[1])
    except OSError:
        pass
    return {"loadavg": load, "mem_total_kb": mem_total, "mem_avail_kb": mem_avail}


def dispatch_file_message(msg: dict) -> dict | None:
    t = msg.get("type")
    payload = msg.get("payload") or {}
    if t == "file.list":
        path = str(payload.get("path") or ".")
        try:
            entries = list_dir(path)
            return {"ok": True, "entries": entries}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
    if t == "file.read_begin":
        path = str(payload.get("path"))
        chunk_size = int(payload.get("chunk_size") or 65536)
        try:
            data, more = read_file_b64(path, 0, chunk_size)
            return {
                "offset": len(data),
                "chunk": base64.b64encode(data).decode("ascii"),
                "more": more,
            }
        except OSError as e:
            return {"error": str(e)}
    if t == "file.read_next":
        path = str(payload.get("path"))
        offset = int(payload.get("offset") or 0)
        chunk_size = int(payload.get("chunk_size") or 65536)
        try:
            data, more = read_file_b64(path, offset, chunk_size)
            return {
                "offset": offset + len(data),
                "chunk": base64.b64encode(data).decode("ascii"),
                "more": more,
            }
        except OSError as e:
            return {"error": str(e)}
    if t == "file.write_begin":
        path = str(payload.get("path"))
        try:
            write_file_begin(path)
            return {"ok": True}
        except OSError as e:
            return {"error": str(e)}
    if t == "file.write_chunk":
        path = str(payload.get("path"))
        chunk_b64 = str(payload.get("chunk") or "")
        append = bool(payload.get("append"))
        try:
            write_file_chunk(path, chunk_b64, append)
            return {"ok": True}
        except OSError as e:
            return {"error": str(e)}
    if t == "proc.list":
        return proc_snapshot()
    if t == "sys.stats":
        return sys_stats()
    return None
