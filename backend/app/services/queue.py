"""Núcleo da fila: emissão, seleção da próxima senha e transições de estado.

Concorrência:
* numeração: `UPDATE ticket_sequences SET last_number = last_number + 1 ... RETURNING`
  é atômico (bloqueia a linha até o commit) tanto no PostgreSQL quanto no SQLite;
  a UNIQUE (ticket_type_id, seq_date, number) é a rede de segurança final.
* chamada/transições: `UPDATE tickets ... WHERE id=? AND status IN (...)` — só um
  atendente "ganha" a mesma senha; o outro recebe rowcount=0 e tenta a próxima.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import config
from ..db import utcnow
from ..models import (
    ACTIVE_STATUSES,
    Counter,
    Priority,
    QueueEvent,
    Ticket,
    TicketSequence,
    TicketType,
    User,
)
from . import settings_service

WAITING = "AGUARDANDO"


class QueueError(Exception):
    def __init__(self, message: str, status_code: int = 409, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}


def local_today() -> date:
    return datetime.now(config.tz).date()


def local_date_of(dt: datetime) -> date:
    return dt.astimezone(config.tz).date()


# ---------------------------------------------------------------------------
# Emissão
# ---------------------------------------------------------------------------
def _next_number(db: Session, type_id: int, seq_date: date) -> int:
    stmt = (
        update(TicketSequence)
        .where(TicketSequence.ticket_type_id == type_id, TicketSequence.seq_date == seq_date)
        .values(last_number=TicketSequence.last_number + 1)
        .returning(TicketSequence.last_number)
    )
    for _ in range(3):
        row = db.execute(stmt).first()
        if row:
            return int(row[0])
        # primeira senha do dia: cria a linha (outra transação pode criar ao mesmo tempo)
        try:
            with db.begin_nested():
                db.execute(insert(TicketSequence).values(ticket_type_id=type_id, seq_date=seq_date, last_number=0))
        except IntegrityError:
            pass
    raise QueueError("Não foi possível gerar a numeração. Tente novamente.", 503)


def format_code(prefix: str, number: int, digits: int, sep: str) -> str:
    return f"{prefix}{sep}{number:0{digits}d}"


def issue_ticket(db: Session, type_id: int, priority_id: int | None, user: User | None,
                 computer_id: int | None = None) -> Ticket:
    ttype = db.get(TicketType, type_id)
    if ttype is None or not ttype.active:
        raise QueueError("Tipo de atendimento inexistente ou inativo.", 422)
    priority = None
    if ttype.requires_category:
        if priority_id is None:
            raise QueueError("Selecione a categoria de prioridade.", 422)
        priority = db.get(Priority, priority_id)
        if priority is None or not priority.active:
            raise QueueError("Categoria de prioridade inexistente ou inativa.", 422)
    st = settings_service.get_all(db)
    today = local_today()
    seq_date = today if st["queue.reset_daily"] else date(2000, 1, 1)
    number = _next_number(db, ttype.id, seq_date)
    code = format_code(ttype.prefix, number, int(st["ticket.digits"]), st["ticket.separator"])
    ticket = Ticket(
        code=code, number=number, ticket_type_id=ttype.id, priority_id=priority.id if priority else None,
        status=WAITING, service_date=today, seq_date=seq_date, created_by=user.id if user else None,
        computer_id=computer_id,
    )
    db.add(ticket)
    db.flush()
    add_event(db, ticket, "CRIADA", None, WAITING, user, None,
              {"type": ttype.code, "category": priority.code if priority else None})
    return ticket


def add_event(db: Session, ticket: Ticket, event_type: str, from_status: str | None, to_status: str | None,
              user: User | None, counter_id: int | None, details: dict | None = None) -> None:
    db.add(QueueEvent(ticket_id=ticket.id, event_type=event_type, from_status=from_status,
                      to_status=to_status, user_id=user.id if user else None, counter_id=counter_id,
                      details=details))


# ---------------------------------------------------------------------------
# Seleção da próxima senha (função pura + consulta)
# ---------------------------------------------------------------------------
@dataclass
class Cand:
    id: int
    created_at: datetime
    level: int  # ticket_types.priority_level
    rank: int  # priorities.rank (menor primeiro); 999 sem categoria
    type_position: int

    @property
    def is_priority(self) -> bool:
        return self.level > 0

    def sort_key(self):
        return (-self.level, self.rank, self.created_at, self.id)


def select_next(cands: list[Cand], streak: int, now: datetime, max_consecutive: int, aging_minutes: int) -> Cand | None:
    """Regras (todas configuráveis):
    1. Envelhecimento: senha comum esperando ≥ `aging_minutes` passa à frente (a mais antiga primeiro).
    2. Limite de prioritárias seguidas: após `max_consecutive`, chama uma comum (se houver).
    3. Caso contrário: maior nível do tipo → menor `rank` da categoria → ordem de chegada.
    """
    if not cands:
        return None
    normals = [c for c in cands if not c.is_priority]
    if aging_minutes > 0 and normals:
        limit = now - timedelta(minutes=aging_minutes)
        aged = [c for c in normals if c.created_at <= limit]
        if aged:
            return min(aged, key=lambda c: (c.created_at, c.id))
    if max_consecutive > 0 and streak >= max_consecutive and normals:
        return min(normals, key=lambda c: (c.type_position, c.created_at, c.id))
    return min(cands, key=Cand.sort_key)


def simulate_order(cands: list[Cand], streak: int, now: datetime, max_consecutive: int, aging_minutes: int) -> list[int]:
    """Ordem prevista de chamada (para a tela de fila)."""
    pool = list(cands)
    out: list[int] = []
    while pool:
        pick = select_next(pool, streak, now, max_consecutive, aging_minutes)
        assert pick is not None
        pool.remove(pick)
        out.append(pick.id)
        streak = streak + 1 if pick.is_priority else 0
    return out


def _to_cand(t: Ticket) -> Cand:
    return Cand(id=t.id, created_at=t.created_at, level=t.ticket_type.priority_level,
                rank=t.priority.rank if t.priority else 999, type_position=t.ticket_type.position)


def waiting_tickets(db: Session, counter: Counter | None = None) -> list[Ticket]:
    q = select(Ticket).where(Ticket.status == WAITING, Ticket.service_date == local_today())
    if counter is not None and counter.accepted_type_ids:
        q = q.where(Ticket.ticket_type_id.in_(list(counter.accepted_type_ids)))
    return list(db.scalars(q).unique())


def priority_streak(db: Session) -> int:
    """Quantas chamadas prioritárias consecutivas aconteceram por último (hoje)."""
    rows = db.scalars(
        select(Ticket).where(Ticket.called_at.is_not(None), Ticket.service_date == local_today())
        .order_by(Ticket.called_at.desc(), Ticket.id.desc()).limit(50)
    ).unique()
    n = 0
    for t in rows:
        if t.ticket_type.priority_level > 0:
            n += 1
        else:
            break
    return n


def ordered_waiting(db: Session, counter: Counter | None = None) -> list[Ticket]:
    st = settings_service.get_all(db)
    tickets = waiting_tickets(db, counter)
    by_id = {t.id: t for t in tickets}
    order = simulate_order([_to_cand(t) for t in tickets], priority_streak(db), utcnow(),
                           int(st["queue.max_consecutive_priority"]), int(st["queue.aging_minutes"]))
    return [by_id[i] for i in order]


# ---------------------------------------------------------------------------
# Transições
# ---------------------------------------------------------------------------
def active_ticket_of(db: Session, user: User) -> Ticket | None:
    return db.scalars(
        select(Ticket).where(Ticket.attendant_id == user.id, Ticket.status.in_(ACTIVE_STATUSES))
        .order_by(Ticket.id.desc()).limit(1)
    ).unique().first()


def _claim(db: Session, ticket_id: int, from_statuses: tuple[str, ...], values: dict) -> bool:
    res = db.execute(
        update(Ticket).where(Ticket.id == ticket_id, Ticket.status.in_(from_statuses))
        .values(updated_at=utcnow(), **values)
    )
    return res.rowcount == 1


def _require_counter(db: Session, counter_id: int | None) -> Counter:
    if counter_id is None:
        raise QueueError("Selecione seu guichê antes de chamar senhas.", 422)
    counter = db.get(Counter, counter_id)
    if counter is None or not counter.active:
        raise QueueError("Guichê inexistente ou inativo.", 422)
    return counter


def call_next(db: Session, user: User, counter_id: int | None) -> Ticket | None:
    counter = _require_counter(db, counter_id)
    current = active_ticket_of(db, user)
    if current is not None:
        raise QueueError(f"Encerre o atendimento da senha {current.code} antes de chamar a próxima.", 409,
                         {"ticket_id": current.id})
    st = settings_service.get_all(db)
    max_consec = int(st["queue.max_consecutive_priority"])
    aging = int(st["queue.aging_minutes"])
    now = utcnow()
    for _ in range(20):  # concorrência: se perder a disputa, tenta a próxima
        cands = [_to_cand(t) for t in waiting_tickets(db, counter)]
        pick = select_next(cands, priority_streak(db), now, max_consec, aging)
        if pick is None:
            return None
        if _claim(db, pick.id, (WAITING,), dict(status="CHAMADA", called_at=now, last_called_at=now,
                                                 counter_id=counter.id, attendant_id=user.id, recall_count=0)):
            ticket = db.get(Ticket, pick.id)
            db.refresh(ticket)
            add_event(db, ticket, "CHAMADA", WAITING, "CHAMADA", user, counter.id)
            return ticket
    raise QueueError("Fila muito movimentada. Tente novamente.", 503)


def call_specific(db: Session, user: User, ticket_id: int, counter_id: int | None) -> Ticket:
    counter = _require_counter(db, counter_id)
    current = active_ticket_of(db, user)
    if current is not None:
        raise QueueError(f"Encerre o atendimento da senha {current.code} antes de chamar outra.", 409,
                         {"ticket_id": current.id})
    ticket = _get(db, ticket_id)
    now = utcnow()
    prev = ticket.status
    if not _claim(db, ticket_id, (WAITING, "NAO_COMPARECEU"),
                  dict(status="CHAMADA", called_at=ticket.called_at or now, last_called_at=now,
                       counter_id=counter.id, attendant_id=user.id, recall_count=0, finished_at=None,
                       status_reason=None)):
        raise QueueError(f"A senha {ticket.code} não pode ser chamada (situação: {ticket.status}).", 409)
    db.refresh(ticket)
    add_event(db, ticket, "CHAMADA", prev, "CHAMADA", user, counter.id, {"manual": True})
    return ticket


def _get(db: Session, ticket_id: int) -> Ticket:
    t = db.get(Ticket, ticket_id)
    if t is None:
        raise QueueError("Senha não encontrada.", 404)
    return t


def _check_owner(ticket: Ticket, user: User, can_override: bool) -> None:
    if ticket.attendant_id is not None and ticket.attendant_id != user.id and not can_override:
        raise QueueError("Esta senha está sendo atendida por outro usuário.", 403)


def recall(db: Session, user: User, ticket_id: int, can_override: bool) -> Ticket:
    ticket = _get(db, ticket_id)
    _check_owner(ticket, user, can_override)
    prev = ticket.status
    if not _claim(db, ticket_id, ("CHAMADA", "RECHAMADA"),
                  dict(status="RECHAMADA", last_called_at=utcnow(), recall_count=Ticket.recall_count + 1)):
        raise QueueError(f"Só é possível rechamar senha já chamada (situação: {ticket.status}).", 409)
    db.refresh(ticket)
    add_event(db, ticket, "RECHAMADA", prev, "RECHAMADA", user, ticket.counter_id, {"n": ticket.recall_count})
    return ticket


def start_attendance(db: Session, user: User, ticket_id: int, can_override: bool) -> Ticket:
    ticket = _get(db, ticket_id)
    _check_owner(ticket, user, can_override)
    prev = ticket.status
    if not _claim(db, ticket_id, ("CHAMADA", "RECHAMADA"), dict(status="EM_ATENDIMENTO", started_at=utcnow())):
        raise QueueError(f"A senha precisa estar chamada para iniciar (situação: {ticket.status}).", 409)
    db.refresh(ticket)
    add_event(db, ticket, "INICIO_ATENDIMENTO", prev, "EM_ATENDIMENTO", user, ticket.counter_id)
    return ticket


def finish(db: Session, user: User, ticket_id: int, can_override: bool) -> Ticket:
    ticket = _get(db, ticket_id)
    _check_owner(ticket, user, can_override)
    prev = ticket.status
    now = utcnow()
    if not _claim(db, ticket_id, ("EM_ATENDIMENTO", "CHAMADA", "RECHAMADA"),
                  dict(status="ATENDIDA", finished_at=now,
                       started_at=func.coalesce(Ticket.started_at, now))):
        raise QueueError(f"A senha não pode ser encerrada (situação: {ticket.status}).", 409)
    db.refresh(ticket)
    add_event(db, ticket, "ENCERRADA", prev, "ATENDIDA", user, ticket.counter_id)
    return ticket


def no_show(db: Session, user: User, ticket_id: int, can_override: bool) -> Ticket:
    ticket = _get(db, ticket_id)
    _check_owner(ticket, user, can_override)
    prev = ticket.status
    if not _claim(db, ticket_id, ("CHAMADA", "RECHAMADA"),
                  dict(status="NAO_COMPARECEU", finished_at=utcnow(), status_reason="Paciente não compareceu")):
        raise QueueError(f"Só é possível marcar não comparecimento de senha chamada (situação: {ticket.status}).", 409)
    db.refresh(ticket)
    add_event(db, ticket, "NAO_COMPARECEU", prev, "NAO_COMPARECEU", user, ticket.counter_id)
    return ticket


def cancel(db: Session, user: User | None, ticket_id: int, reason: str | None) -> Ticket:
    ticket = _get(db, ticket_id)
    prev = ticket.status
    if not _claim(db, ticket_id, (WAITING, "CHAMADA", "RECHAMADA", "NAO_COMPARECEU"),
                  dict(status="CANCELADA", finished_at=utcnow(), status_reason=(reason or "Cancelada")[:255])):
        raise QueueError(f"A senha não pode ser cancelada (situação: {ticket.status}).", 409)
    db.refresh(ticket)
    add_event(db, ticket, "CANCELADA", prev, "CANCELADA", user, ticket.counter_id, {"reason": reason})
    return ticket


def expire_stale(db: Session) -> int:
    """Rotina de virada do dia: encerra pendências de dias anteriores SEM apagar histórico."""
    today = local_today()
    stale = list(db.scalars(
        select(Ticket).where(Ticket.service_date < today,
                             Ticket.status.in_((WAITING, "CHAMADA", "RECHAMADA", "EM_ATENDIMENTO")))
    ).unique())
    n = 0
    for t in stale:
        prev = t.status
        if _claim(db, t.id, (prev,), dict(status="CANCELADA", finished_at=utcnow(),
                                          status_reason="Encerrada automaticamente na virada do dia")):
            add_event(db, t, "EXPIRADA", prev, "CANCELADA", None, t.counter_id)
            n += 1
    return n


def counts_today(db: Session) -> dict:
    rows = db.execute(
        select(Ticket.status, func.count()).where(Ticket.service_date == local_today()).group_by(Ticket.status)
    ).all()
    c = {s: n for s, n in rows}
    return {
        "total": sum(c.values()), "waiting": c.get("AGUARDANDO", 0),
        "calling": c.get("CHAMADA", 0) + c.get("RECHAMADA", 0),
        "in_service": c.get("EM_ATENDIMENTO", 0), "done": c.get("ATENDIDA", 0),
        "no_show": c.get("NAO_COMPARECEU", 0), "cancelled": c.get("CANCELADA", 0),
    }
