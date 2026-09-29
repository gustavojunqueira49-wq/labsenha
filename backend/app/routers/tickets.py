from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Auth, current_auth_ready, require
from ..events import hub
from ..models import Attendant, Counter, Priority, QueueEvent, Ticket, TicketType, User
from ..serializers import counter_out, priority_out, ticket_out, type_out
from ..services import printing, queue, settings_service

router = APIRouter(tags=["Senhas e fila"])


class IssueIn(BaseModel):
    ticket_type_id: int
    priority_id: int | None = None


class CallIn(BaseModel):
    counter_id: int | None = None


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


def _my_counter(db: Session, auth: Auth, requested: int | None) -> int | None:
    if requested:
        return requested
    att = db.scalars(select(Attendant).where(Attendant.user_id == auth.user.id)).first()
    return att.counter_id if att else None


def _publish(event: str, ticket: Ticket, db: Session, **extra) -> None:
    hub.publish(event, {"ticket": ticket_out(ticket), **extra})
    hub.publish("queue.updated", {"counts": queue.counts_today(db)})


def _can_override(auth: Auth) -> bool:
    return auth.can("ticket.override")


# ---- catálogos para as telas -------------------------------------------------
@router.get("/ticket-types")
def ticket_types(auth: Auth = Depends(current_auth_ready), db: Session = Depends(get_db)):
    q = select(TicketType).where(TicketType.active.is_(True)).order_by(TicketType.position, TicketType.id)
    return [type_out(t) for t in db.scalars(q)]


@router.get("/priorities")
def priorities(auth: Auth = Depends(current_auth_ready), db: Session = Depends(get_db)):
    q = select(Priority).where(Priority.active.is_(True)).order_by(Priority.rank, Priority.id)
    return [priority_out(p) for p in db.scalars(q)]


@router.get("/counters")
def counters(auth: Auth = Depends(current_auth_ready), db: Session = Depends(get_db)):
    occupants = {a.counter_id: a for a in db.scalars(select(Attendant).where(Attendant.counter_id.is_not(None)))}
    out = []
    for c in db.scalars(select(Counter).where(Counter.active.is_(True)).order_by(Counter.position, Counter.id)):
        occ = occupants.get(c.id)
        u = db.get(User, occ.user_id) if occ else None
        out.append({**counter_out(c), "occupied_by": u.full_name if u else None,
                    "occupied_by_id": u.id if u else None})
    return out


# ---- emissão ----------------------------------------------------------------
@router.post("/tickets", status_code=201)
def create_ticket(body: IssueIn, auth: Auth = Depends(require("ticket.create")), db: Session = Depends(get_db)):
    ticket = queue.issue_ticket(db, body.ticket_type_id, body.priority_id, auth.user, auth.session.computer_id)
    job = None
    if settings_service.get(db, "print.auto"):
        job = printing.create_ticket_job(db, ticket, auth.user)  # mesma transação: senha e impressão nunca divergem
    db.commit()
    db.refresh(ticket)
    _publish("ticket.created", ticket, db, print_job_id=job.id if job else None)
    if job:
        hub.publish("print.job", {"job_id": job.id, "status": job.status})
    return {"ticket": ticket_out(ticket), "print_job_id": job.id if job else None}


@router.post("/tickets/{ticket_id}/reprint")
def reprint(ticket_id: int, auth: Auth = Depends(require("print.reprint")), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404, "Senha não encontrada.")
    job = printing.create_ticket_job(db, ticket, auth.user)
    audit(db, auth.user, "senha.reimpressa", "ticket", ticket.id, {"code": ticket.code}, auth.ip)
    db.commit()
    hub.publish("print.job", {"job_id": job.id, "status": job.status})
    return {"print_job_id": job.id}


# ---- consultas ----------------------------------------------------------------
@router.get("/tickets/waiting")
def waiting(counter_id: int | None = None, auth: Auth = Depends(require("ticket.view")), db: Session = Depends(get_db)):
    counter = db.get(Counter, counter_id) if counter_id else None
    return {"tickets": [ticket_out(t) for t in queue.ordered_waiting(db, counter)], "counts": queue.counts_today(db)}


@router.get("/tickets/current")
def current(auth: Auth = Depends(require("ticket.call")), db: Session = Depends(get_db)):
    t = queue.active_ticket_of(db, auth.user)
    return {"ticket": ticket_out(t) if t else None, "counts": queue.counts_today(db)}


@router.get("/tickets")
def list_tickets(day: date | None = None, status: str | None = None, code: str | None = None,
                 limit: int = Query(200, ge=1, le=1000),
                 auth: Auth = Depends(require("ticket.view", "history.view")), db: Session = Depends(get_db)):
    q = select(Ticket).where(Ticket.service_date == (day or queue.local_today()))
    if status:
        q = q.where(Ticket.status == status.upper())
    if code:
        q = q.where(Ticket.code.ilike(f"%{code.strip()}%"))
    return {"tickets": [ticket_out(t) for t in db.scalars(q.order_by(Ticket.id.desc()).limit(limit)).unique()]}


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, auth: Auth = Depends(require("ticket.view", "history.view")), db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if t is None:
        raise HTTPException(404, "Senha não encontrada.")
    events = db.scalars(select(QueueEvent).where(QueueEvent.ticket_id == t.id).order_by(QueueEvent.id))
    users = {u.id: u.full_name for u in db.scalars(select(User))}
    counters_ = {c.id: c.name for c in db.scalars(select(Counter))}
    return {"ticket": ticket_out(t), "events": [
        {"type": e.event_type, "from": e.from_status, "to": e.to_status, "at": e.created_at.isoformat(),
         "user": users.get(e.user_id), "counter": counters_.get(e.counter_id), "details": e.details}
        for e in events]}


# ---- operações do atendente -------------------------------------------------------
@router.post("/tickets/call-next")
def call_next(body: CallIn, auth: Auth = Depends(require("ticket.call")), db: Session = Depends(get_db)):
    t = queue.call_next(db, auth.user, _my_counter(db, auth, body.counter_id))
    db.commit()
    if t is None:
        return {"ticket": None, "message": "Nenhuma senha aguardando."}
    _publish("ticket.called", t, db, announce=True)
    return {"ticket": ticket_out(t)}


@router.post("/tickets/{ticket_id}/call")
def call_specific(ticket_id: int, body: CallIn, auth: Auth = Depends(require("ticket.call")), db: Session = Depends(get_db)):
    t = queue.call_specific(db, auth.user, ticket_id, _my_counter(db, auth, body.counter_id))
    db.commit()
    _publish("ticket.called", t, db, announce=True)
    return {"ticket": ticket_out(t)}


@router.post("/tickets/{ticket_id}/recall")
def recall(ticket_id: int, auth: Auth = Depends(require("ticket.call")), db: Session = Depends(get_db)):
    t = queue.recall(db, auth.user, ticket_id, _can_override(auth))
    db.commit()
    _publish("ticket.recalled", t, db, announce=True)
    return {"ticket": ticket_out(t)}


@router.post("/tickets/{ticket_id}/attend")
def attend(ticket_id: int, auth: Auth = Depends(require("ticket.call")), db: Session = Depends(get_db)):
    t = queue.start_attendance(db, auth.user, ticket_id, _can_override(auth))
    db.commit()
    _publish("ticket.started", t, db)
    return {"ticket": ticket_out(t)}


@router.post("/tickets/{ticket_id}/finish")
def finish(ticket_id: int, auth: Auth = Depends(require("ticket.call")), db: Session = Depends(get_db)):
    t = queue.finish(db, auth.user, ticket_id, _can_override(auth))
    db.commit()
    _publish("ticket.attended", t, db)
    return {"ticket": ticket_out(t)}


@router.post("/tickets/{ticket_id}/no-show")
def no_show(ticket_id: int, auth: Auth = Depends(require("ticket.call")), db: Session = Depends(get_db)):
    t = queue.no_show(db, auth.user, ticket_id, _can_override(auth))
    db.commit()
    _publish("ticket.no_show", t, db)
    return {"ticket": ticket_out(t)}


@router.post("/tickets/{ticket_id}/cancel")
def cancel(ticket_id: int, body: ReasonIn, auth: Auth = Depends(require("ticket.cancel")), db: Session = Depends(get_db)):
    t = queue.cancel(db, auth.user, ticket_id, body.reason)
    audit(db, auth.user, "senha.cancelada", "ticket", t.id, {"code": t.code, "reason": body.reason}, auth.ip)
    db.commit()
    _publish("ticket.cancelled", t, db)
    return {"ticket": ticket_out(t)}


# ---- painel ----------------------------------------------------------------------
@router.get("/panel/state")
def panel_state(auth: Auth = Depends(require("panel.view", "ticket.view")), db: Session = Depends(get_db)):
    st = settings_service.get_all(db)
    n = int(st["panel.show_history"])
    rows = list(db.scalars(
        select(Ticket).where(Ticket.last_called_at.is_not(None), Ticket.service_date == queue.local_today(),
                             Ticket.status != "CANCELADA")
        .order_by(Ticket.last_called_at.desc(), Ticket.id.desc()).limit(n + 1)).unique())
    cur = rows[0] if rows else None
    return {"current": ticket_out(cur) if cur else None, "history": [ticket_out(t) for t in rows[1:n + 1]],
            "counts": queue.counts_today(db), "settings": settings_service.public_view(st)}
