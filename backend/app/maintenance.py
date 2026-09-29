"""Tarefas de fundo: agentes offline, impressoras de rede, virada do dia, backup automático."""
from __future__ import annotations

import asyncio
import logging
import time

from . import db as dbmod
from .events import hub
from .services import backup as backup_svc
from .services import printing, queue

log = logging.getLogger("maintenance")
_state = {"tick": 0, "last_expire": 0.0, "last_backup_check": 0.0}


def tick() -> None:
    events: list[str] = []
    with dbmod.SessionLocal() as db:
        events += printing.detect_agent_transitions(db)
        printing.reset_stale(db)
        printing.assign_orphans(db)
        events += printing.process_network_jobs(db)
        db.commit()
        now = time.monotonic()
        if now - _state["last_expire"] > 300:
            _state["last_expire"] = now
            n = queue.expire_stale(db)
            db.commit()
            if n:
                events.append("queue.updated")
        if now - _state["last_backup_check"] > 60:
            _state["last_backup_check"] = now
            if backup_svc.due_for_auto(db):
                rec = backup_svc.create_backup(db, "AUTO")
                log.info("Backup automático: %s (%s)", rec.filename, rec.status)
    for e in set(events):
        hub.publish(e, {})


async def loop(interval: int) -> None:
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:  # banco fora do ar etc.: registra e tenta de novo
            log.exception("Falha na manutenção (será repetida)")
        await asyncio.sleep(interval)
