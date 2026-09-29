from __future__ import annotations

from .db import utcnow
from .models import Counter, PrintJob, Priority, Ticket, TicketType, User


def dt(v):
    return v.isoformat() if v else None


def type_out(t: TicketType) -> dict:
    return {"id": t.id, "code": t.code, "name": t.name, "prefix": t.prefix, "color": t.color,
            "position": t.position, "priority_level": t.priority_level, "requires_category": t.requires_category,
            "description": t.description, "active": t.active}


def priority_out(p: Priority) -> dict:
    return {"id": p.id, "code": p.code, "name": p.name, "description": p.description,
            "legal_basis": p.legal_basis, "rank": p.rank, "active": p.active}


def counter_out(c: Counter) -> dict:
    return {"id": c.id, "code": c.code, "name": c.name, "spoken_name": c.spoken_name or c.name,
            "position": c.position, "active": c.active, "accepted_type_ids": c.accepted_type_ids or []}


def user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role.code,
            "role_name": u.role.name, "active": u.active, "must_change_password": u.must_change_password,
            "locked_until": dt(u.locked_until), "last_login_at": dt(u.last_login_at), "created_at": dt(u.created_at)}


def ticket_out(t: Ticket) -> dict:
    """Nunca contém dados do paciente — o sistema não os armazena."""
    now = utcnow()
    wait_end = t.called_at or (now if t.status == "AGUARDANDO" else None)
    return {
        "id": t.id, "code": t.code, "status": t.status, "service_date": t.service_date.isoformat(),
        "type": {"id": t.ticket_type.id, "name": t.ticket_type.name, "prefix": t.ticket_type.prefix,
                 "color": t.ticket_type.color, "priority_level": t.ticket_type.priority_level},
        "category": t.priority.name if t.priority else None,
        "counter": {"id": t.counter.id, "name": t.counter.name,
                    "spoken_name": t.counter.spoken_name or t.counter.name} if t.counter else None,
        "attendant": t.attendant.full_name if t.attendant else None,
        "attendant_id": t.attendant_id,
        "created_at": dt(t.created_at), "called_at": dt(t.called_at), "last_called_at": dt(t.last_called_at),
        "started_at": dt(t.started_at), "finished_at": dt(t.finished_at),
        "recall_count": t.recall_count, "status_reason": t.status_reason,
        "wait_seconds": int((wait_end - t.created_at).total_seconds()) if wait_end else None,
    }


def job_out(j: PrintJob) -> dict:
    return {"id": j.id, "ticket_id": j.ticket_id, "code": (j.payload or {}).get("code"), "kind": j.kind,
            "status": j.status, "attempts": j.attempts, "last_error": j.last_error,
            "printer_id": j.printer_id, "printer": j.printer.name if j.printer else None,
            "created_at": dt(j.created_at), "printed_at": dt(j.printed_at),
            "next_attempt_at": dt(j.next_attempt_at)}
