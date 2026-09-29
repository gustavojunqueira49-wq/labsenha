"""Hub de eventos em tempo real (WebSocket).

Os endpoints são síncronos (rodam em threads); `publish` é thread-safe e entrega
as mensagens no loop asyncio onde os WebSockets vivem. Publique SEMPRE depois do commit.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone

log = logging.getLogger("events")


class Hub:
    def __init__(self) -> None:
        self._clients: dict[int, tuple[asyncio.Queue, dict]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._next = 0
        self.history: list[dict] = []  # para testes/diagnóstico (últimos 200)

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def register(self, meta: dict) -> tuple[int, asyncio.Queue]:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            self._next += 1
            cid = self._next
            self._clients[cid] = (q, meta)
        return cid, q

    def unregister(self, cid: int) -> None:
        with self._lock:
            self._clients.pop(cid, None)

    def clients_info(self) -> list[dict]:
        with self._lock:
            return [dict(m) for _, m in self._clients.values()]

    def publish(self, event_type: str, data: dict | None = None) -> None:
        msg = {"type": event_type, "data": data or {}, "at": datetime.now(timezone.utc).isoformat()}
        with self._lock:
            self.history.append(msg)
            del self.history[:-200]
            targets = [q for q, _ in self._clients.values()]
        payload = json.dumps(msg, default=str)
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        for q in targets:
            try:
                loop.call_soon_threadsafe(self._put, q, payload)
            except RuntimeError:  # loop encerrado
                pass

    @staticmethod
    def _put(q: asyncio.Queue, payload: str) -> None:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:  # cliente lento: descarta o mais antigo
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except Exception:
                pass


hub = Hub()
