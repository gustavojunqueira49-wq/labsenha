"""Fila de impressão: jobs persistidos no banco (nunca se perdem) + agentes/impressoras."""
from __future__ import annotations

import base64
import hashlib
import secrets
import socket
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import PrintAgent, PrintJob, Printer, Ticket, User
from . import escpos, settings_service

AGENT_ONLINE_SECONDS = 20
STALE_SENDING_SECONDS = 60


def new_agent_token() -> tuple[str, str]:
    token = "pa_" + secrets.token_urlsafe(30)
    return token, hashlib.sha256(token.encode()).hexdigest()


def agent_is_online(agent: PrintAgent) -> bool:
    return bool(agent.active and agent.last_seen_at
                and utcnow() - agent.last_seen_at <= timedelta(seconds=AGENT_ONLINE_SECONDS))


def default_printer(db: Session) -> Printer | None:
    p = db.scalars(select(Printer).where(Printer.active.is_(True), Printer.is_default.is_(True))).first()
    if p is None:
        p = db.scalars(select(Printer).where(Printer.active.is_(True)).order_by(Printer.id)).first()
    return p


def create_ticket_job(db: Session, ticket: Ticket, user: User | None, printer_id: int | None = None) -> PrintJob:
    printer = db.get(Printer, printer_id) if printer_id else default_printer(db)
    job = PrintJob(
        ticket_id=ticket.id, printer_id=printer.id if printer else None, kind="TICKET",
        created_by=user.id if user else None,
        payload={"kind": "TICKET", "code": ticket.code, "type_name": ticket.ticket_type.name,
                 "category_name": ticket.priority.name if ticket.priority else None,
                 "is_priority": ticket.ticket_type.priority_level > 0,
                 "issued_at": ticket.created_at.isoformat()},
    )
    db.add(job)
    db.flush()
    return job


def create_test_job(db: Session, printer: Printer, user: User | None) -> PrintJob:
    job = PrintJob(printer_id=printer.id, kind="TEST", created_by=user.id if user else None,
                   payload={"kind": "TEST", "issued_at": utcnow().isoformat()})
    db.add(job)
    db.flush()
    return job


def assign_orphans(db: Session) -> int:
    """Jobs criados quando não havia impressora ficam esperando; ao configurar uma, são atribuídos."""
    p = default_printer(db)
    if p is None:
        return 0
    res = db.execute(update(PrintJob).where(PrintJob.printer_id.is_(None), PrintJob.status.in_(("PENDENTE", "ERRO")))
                     .values(printer_id=p.id))
    return res.rowcount or 0


def reset_stale(db: Session) -> int:
    limit = utcnow() - timedelta(seconds=STALE_SENDING_SECONDS)
    res = db.execute(update(PrintJob).where(PrintJob.status == "ENVIANDO", PrintJob.claimed_at < limit)
                     .values(status="PENDENTE"))
    return res.rowcount or 0


def render_job(db: Session, job: PrintJob, printer: Printer) -> dict:
    st = settings_service.get_all(db)
    lines = escpos.build_lines(job.payload or {}, st)
    data = escpos.render_escpos(lines, printer)
    return {
        "id": job.id, "kind": job.kind, "attempts": job.attempts, "code": (job.payload or {}).get("code"),
        "escpos_b64": base64.b64encode(data).decode(),
        "text": escpos.render_text(lines, printer.chars_per_line),
        "cut": printer.cut, "encoding": printer.encoding,
    }


def _claim_job(db: Session, job_id: int) -> bool:
    res = db.execute(update(PrintJob).where(PrintJob.id == job_id, PrintJob.status == "PENDENTE")
                     .values(status="ENVIANDO", claimed_at=utcnow()))
    return res.rowcount == 1


def claim_for_agent(db: Session, agent: PrintAgent, limit: int = 5) -> list[dict]:
    reset_stale(db)
    now = utcnow()
    printers = {p.id: p for p in db.scalars(select(Printer).where(Printer.agent_id == agent.id, Printer.active.is_(True)))}
    if not printers:
        return []
    jobs = list(db.scalars(
        select(PrintJob).where(PrintJob.status == "PENDENTE", PrintJob.printer_id.in_(list(printers)),
                               (PrintJob.next_attempt_at.is_(None)) | (PrintJob.next_attempt_at <= now))
        .order_by(PrintJob.id).limit(limit)
    ).unique())
    out = []
    for job in jobs:
        if _claim_job(db, job.id):
            out.append(render_job(db, job, printers[job.printer_id]))
    return out


def report_result(db: Session, printer_ids: set[int] | None, job_id: int, ok: bool, error: str | None,
                  printer_status: str | None = None) -> PrintJob:
    job = db.get(PrintJob, job_id)
    if job is None or (printer_ids is not None and job.printer_id not in printer_ids):
        raise LookupError("job")
    now = utcnow()
    max_attempts = int(settings_service.get(db, "print.max_attempts"))
    if ok:
        job.status, job.printed_at, job.last_error, job.next_attempt_at = "IMPRESSO", now, None, None
        if job.printer:
            job.printer.last_print_at = now
            job.printer.status, job.printer.status_detail, job.printer.status_at = "ONLINE", None, now
    else:
        job.attempts += 1
        job.last_error = (error or "Erro desconhecido")[:500]
        if job.attempts >= max_attempts:
            job.status = "ERRO"
        else:
            job.status = "PENDENTE"
            job.next_attempt_at = now + timedelta(seconds=min(60, 2 * job.attempts))
        if job.printer:
            job.printer.status = printer_status or "ERRO"
            job.printer.status_detail, job.printer.status_at = job.last_error, now
    return job


def retry_job(db: Session, job: PrintJob, printer_id: int | None = None) -> PrintJob:
    if printer_id:
        job.printer_id = printer_id
    elif job.printer_id is None:
        p = default_printer(db)
        job.printer_id = p.id if p else None
    job.status, job.next_attempt_at, job.last_error = "PENDENTE", None, None
    return job


def heartbeat(db: Session, agent: PrintAgent, info: dict) -> list[str]:
    """Atualiza agente + impressoras. Retorna lista de eventos a publicar."""
    now = utcnow()
    agent.last_seen_at = now
    agent.version = (info.get("version") or agent.version or "")[:30]
    agent.hostname = (info.get("hostname") or agent.hostname or "")[:120]
    events = []
    if not agent.was_online:
        agent.was_online = True
        events.append("agent.status")
    status = (info.get("printer_status") or "").upper() or None
    if status:
        for p in db.scalars(select(Printer).where(Printer.agent_id == agent.id)):
            changed = (p.status, p.status_detail) != (status, info.get("printer_detail"))
            p.status, p.status_detail, p.status_at = status, (info.get("printer_detail") or None), now
            if info.get("printer_name"):
                p.system_name = info["printer_name"][:120]
            if changed:
                events.append("printer.status")
    agent.last_error = (info.get("printer_detail") or None) if status and status != "ONLINE" else None
    return events


# ---- Impressoras de rede (cenário B): o próprio servidor envia por TCP 9100 ------
def _send_tcp(host: str, port: int, data: bytes, timeout: float = 4.0) -> None:
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(data)


def process_network_jobs(db: Session) -> list[str]:
    events: list[str] = []
    now = utcnow()
    for printer in db.scalars(select(Printer).where(Printer.connection == "NETWORK", Printer.active.is_(True))):
        if not printer.host:
            continue
        reset_stale(db)
        jobs = list(db.scalars(
            select(PrintJob).where(PrintJob.status == "PENDENTE", PrintJob.printer_id == printer.id,
                                   (PrintJob.next_attempt_at.is_(None)) | (PrintJob.next_attempt_at <= now))
            .order_by(PrintJob.id).limit(5)).unique())
        if not jobs:
            # sonda de status a cada ~30s
            if not printer.status_at or now - printer.status_at > timedelta(seconds=30):
                old = printer.status
                try:
                    socket.create_connection((printer.host, printer.port), timeout=2).close()
                    printer.status, printer.status_detail = "ONLINE", None
                except OSError as e:
                    printer.status, printer.status_detail = "OFFLINE", str(e)[:200]
                printer.status_at = now
                if old != printer.status:
                    events.append("printer.status")
            continue
        for job in jobs:
            if not _claim_job(db, job.id):
                continue
            payload = render_job(db, job, printer)
            try:
                _send_tcp(printer.host, printer.port, base64.b64decode(payload["escpos_b64"]))
                report_result(db, None, job.id, True, None)
            except OSError as e:
                report_result(db, None, job.id, False, f"Impressora de rede indisponível: {e}", "OFFLINE")
                events.append("printer.status")
                break
            events.append("print.job")
    return events


def agents_overview(db: Session) -> list[dict]:
    out = []
    for a in db.scalars(select(PrintAgent).order_by(PrintAgent.id)):
        out.append({"id": a.id, "name": a.name, "online": agent_is_online(a), "active": a.active,
                    "last_seen_at": a.last_seen_at, "hostname": a.hostname, "version": a.version,
                    "computer_id": a.computer_id, "last_error": a.last_error})
    return out


def queue_counts(db: Session) -> dict:
    rows = db.execute(select(PrintJob.status, func.count()).group_by(PrintJob.status)).all()
    c = {s: n for s, n in rows}
    return {"pending": c.get("PENDENTE", 0) + c.get("ENVIANDO", 0), "error": c.get("ERRO", 0),
            "printed": c.get("IMPRESSO", 0)}


def detect_agent_transitions(db: Session) -> list[str]:
    ev = []
    for a in db.scalars(select(PrintAgent)):
        online = agent_is_online(a)
        if a.was_online and not online:
            a.was_online = False
            for p in db.scalars(select(Printer).where(Printer.agent_id == a.id)):
                p.status, p.status_detail, p.status_at = "OFFLINE", "Agente de impressão sem comunicação", utcnow()
            ev += ["agent.status", "printer.status"]
    return ev
