"""进程内环形日志缓冲，供 Web 实时查看（与 mdm.business Handler 配合）。"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Deque, Dict, List, Tuple

_MAX_LINES = 4000

_lock = threading.Lock()
_buf: Deque[Tuple[int, str]] = deque(maxlen=_MAX_LINES)
_seq = 0


def append_formatted(line: str) -> int:
    global _seq
    with _lock:
        _seq += 1
        sid = _seq
        _buf.append((sid, line))
        return sid


def tail_since(last_id: int, limit: int = 200) -> List[Dict[str, Any]]:
    """返回 id 大于 last_id 的日志条目，按 id 升序，最多 limit 条。"""
    with _lock:
        items = [{"id": i, "line": ln} for i, ln in _buf if i > last_id]
        items.sort(key=lambda x: x["id"])
        return items[:limit]


def tail_last(n: int = 300) -> List[Dict[str, Any]]:
    with _lock:
        return [{"id": i, "line": ln} for i, ln in list(_buf)[-n:]]
