from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import config
from ..db import get_db
from ..deps import Auth, require
from ..events import hub
from ..models import AuditLog, Computer, Counter, Panel, Priority, Setting, Ticket, TicketType
from ..serializers import counter_out, dt, priority_out, type_out
from ..services import seed, settings_service

router = APIRouter(tags=["Administração"])
CFG = "config.manage"
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _flush(db: Session, what: str) -> None:
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Já existe {what} com esse código/nome/prefixo.") from None


def _commit(db: Session, what: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Já existe {what} com esse código/nome/prefixo.") from None


# ---- tipos de atendimento ---------------------------------------------------
class TypeIn(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=2, max_length=80)
    prefix: str = Field(min_length=1, max_length=4, pattern=r"^[A-Za-z0-9]+$")
    color: str = "#2563eb"
    position: int = Field(default=0, ge=0, le=999)
    priority_level: int = Field(default=0, ge=0, le=100)
    requires_category: bool = False
    description: str = Field(default="", max_length=255)
    active: bool = True

    @field_validator("color")
    @classmethod
    def _c(cls, v: str) -> str:
        if not COLOR_RE.match(v):
            raise ValueError("Cor inválida (use #RRGGBB)")
        return v


@router.get("/admin/ticket-types")
def all_types(auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    return [type_out(t) for t in db.scalars(select(TicketType).order_by(TicketType.position, TicketType.id))]


@router.post("/admin/ticket-types", status_code=201)
def create_type(body: TypeIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    t = TicketType(**{**body.model_dump(), "code": body.code.upper(), "prefix": body.prefix.upper()})
    db.add(t)
    _flush(db, "tipo")
    audit(db, auth.user, "tipo.criado", "ticket_type", t.id, body.model_dump(), auth.ip)
    _commit(db, "tipo")
    return type_out(t)


@router.put("/admin/ticket-types/{tid}")
def update_type(tid: int, body: TypeIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    t = db.get(TicketType, tid)
    if t is None:
        raise HTTPException(404, "Tipo não encontrado.")
    old = type_out(t)
    if body.prefix.upper() != t.prefix and db.scalar(select(Ticket.id).where(Ticket.ticket_type_id == tid).limit(1)):
        raise HTTPException(409, "O prefixo não pode ser alterado depois que o tipo emitiu senhas. Crie um novo tipo.")
    for k, v in body.model_dump().items():
        setattr(t, k, v.upper() if k in ("code", "prefix") else v)
    audit(db, auth.user, "tipo.alterado", "ticket_type", t.id, {"antes": old, "depois": body.model_dump()}, auth.ip)
    _commit(db, "tipo")
    return type_out(t)


# ---- prioridades --------------------------------------------------------------
class PriorityIn(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    legal_basis: str = Field(default="", max_length=500)
    rank: int = Field(default=100, ge=0, le=9999)
    active: bool = True


@router.get("/admin/priorities")
def all_priorities(auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    return {"priorities": [priority_out(p) for p in db.scalars(select(Priority).order_by(Priority.rank, Priority.id))],
            "notice": "As categorias e a fundamentação legal aqui cadastradas são configuráveis e devem ser "
                      "validadas pelo hospital (jurídico/administrativo) conforme a legislação vigente."}


@router.post("/admin/priorities", status_code=201)
def create_priority(body: PriorityIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    p = Priority(**{**body.model_dump(), "code": body.code.upper()})
    db.add(p)
    _flush(db, "categoria")
    audit(db, auth.user, "prioridade.criada", "priority", p.id, body.model_dump(), auth.ip)
    _commit(db, "categoria")
    return priority_out(p)


@router.put("/admin/priorities/{pid}")
def update_priority(pid: int, body: PriorityIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    p = db.get(Priority, pid)
    if p is None:
        raise HTTPException(404, "Categoria não encontrada.")
    old = priority_out(p)
    for k, v in body.model_dump().items():
        setattr(p, k, v.upper() if k == "code" else v)
    audit(db, auth.user, "prioridade.alterada", "priority", p.id, {"antes": old, "depois": body.model_dump()}, auth.ip)
    _commit(db, "categoria")
    return priority_out(p)


# ---- guichês ------------------------------------------------------------------
class CounterIn(BaseModel):
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=2, max_length=60)
    spoken_name: str = Field(default="", max_length=80)
    position: int = Field(default=0, ge=0, le=999)
    active: bool = True
    accepted_type_ids: list[int] = []


@router.get("/admin/counters")
def all_counters(auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    return [counter_out(c) for c in db.scalars(select(Counter).order_by(Counter.position, Counter.id))]


@router.post("/admin/counters", status_code=201)
def create_counter(body: CounterIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    c = Counter(**{**body.model_dump(), "code": body.code.upper()})
    db.add(c)
    _flush(db, "guichê")
    audit(db, auth.user, "guiche.criado", "counter", c.id, body.model_dump(), auth.ip)
    _commit(db, "guichê")
    return counter_out(c)


@router.put("/admin/counters/{cid}")
def update_counter(cid: int, body: CounterIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    c = db.get(Counter, cid)
    if c is None:
        raise HTTPException(404, "Guichê não encontrado.")
    for k, v in body.model_dump().items():
        setattr(c, k, v.upper() if k == "code" else v)
    audit(db, auth.user, "guiche.alterado", "counter", c.id, body.model_dump(), auth.ip)
    _commit(db, "guichê")
    return counter_out(c)


# ---- computadores e painéis ---------------------------------------------------
class ComputerIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    ip_address: str | None = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=255)
    active: bool = True


def computer_out(c: Computer) -> dict:
    return {"id": c.id, "name": c.name, "ip_address": c.ip_address, "description": c.description,
            "active": c.active, "last_seen_at": dt(c.last_seen_at)}


@router.get("/admin/computers")
def list_computers(auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    return [computer_out(c) for c in db.scalars(select(Computer).order_by(Computer.name))]


@router.post("/admin/computers", status_code=201)
def create_computer(body: ComputerIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    c = Computer(**body.model_dump())
    db.add(c)
    _flush(db, "computador")
    audit(db, auth.user, "computador.criado", "computer", c.id, body.model_dump(), auth.ip)
    _commit(db, "computador")
    return computer_out(c)


@router.put("/admin/computers/{cid}")
def update_computer(cid: int, body: ComputerIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    c = db.get(Computer, cid)
    if c is None:
        raise HTTPException(404, "Computador não encontrado.")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, auth.user, "computador.alterado", "computer", c.id, body.model_dump(), auth.ip)
    _commit(db, "computador")
    return computer_out(c)


class PanelIn(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=2, max_length=80)
    computer_id: int | None = None
    history_size: int = Field(default=6, ge=1, le=12)
    active: bool = True


def panel_out(p: Panel) -> dict:
    return {"id": p.id, "code": p.code, "name": p.name, "computer_id": p.computer_id,
            "history_size": p.history_size, "active": p.active, "last_seen_at": dt(p.last_seen_at)}


@router.get("/admin/panels")
def list_panels(auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    return [panel_out(p) for p in db.scalars(select(Panel).order_by(Panel.id))]


@router.post("/admin/panels", status_code=201)
def create_panel(body: PanelIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    p = Panel(**{**body.model_dump(), "code": body.code.upper()})
    db.add(p)
    _flush(db, "painel")
    audit(db, auth.user, "painel.criado", "panel", p.id, body.model_dump(), auth.ip)
    _commit(db, "painel")
    return panel_out(p)


@router.put("/admin/panels/{pid}")
def update_panel(pid: int, body: PanelIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    p = db.get(Panel, pid)
    if p is None:
        raise HTTPException(404, "Painel não encontrado.")
    for k, v in body.model_dump().items():
        setattr(p, k, v.upper() if k == "code" else v)
    audit(db, auth.user, "painel.alterado", "panel", p.id, body.model_dump(), auth.ip)
    _commit(db, "painel")
    return panel_out(p)


# ---- configurações ------------------------------------------------------------
@router.get("/admin/settings")
def get_settings(auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    vals = settings_service.get_all(db)
    return {"definitions": [{"key": d.key, "type": d.type, "group": d.group, "label": d.label, "help": d.help,
                             "min": d.min, "max": d.max, "default": d.default, "value": vals[d.key]}
                            for d in settings_service.DEFS]}


@router.put("/admin/settings")
def put_settings(body: dict, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    changed = {}
    for key, raw in body.items():
        d = settings_service.DEF_MAP.get(key)
        if d is None:
            raise HTTPException(422, f"Configuração desconhecida: {key}")
        try:
            val = settings_service.coerce(d, raw)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=val, updated_by=auth.user.id))
        elif row.value != val:
            row.value, row.updated_by = val, auth.user.id
        else:
            continue
        changed[key] = "(imagem)" if d.type == "logo" else val
    audit(db, auth.user, "configuracao.alterada", "settings", None, changed, auth.ip)
    db.commit()
    hub.publish("settings.updated", {"keys": list(changed)})
    return {"changed": list(changed)}


# ---- auditoria ----------------------------------------------------------------
@router.get("/admin/audit")
def audit_list(action: str | None = None, username: str | None = None, day: date | None = None,
               limit: int = Query(200, ge=1, le=1000), auth: Auth = Depends(require("audit.view")),
               db: Session = Depends(get_db)):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
    if username:
        q = q.where(AuditLog.username == username.lower())
    if day:
        start = datetime.combine(day, time.min, tzinfo=config.tz).astimezone(timezone.utc)
        q = q.where(AuditLog.created_at >= start, AuditLog.created_at < start + timedelta(days=1))
    return [{"id": a.id, "at": dt(a.created_at), "username": a.username, "action": a.action, "entity": a.entity,
             "entity_id": a.entity_id, "details": a.details, "ip": a.ip_address}
            for a in db.scalars(q.order_by(AuditLog.id.desc()).limit(limit))]


# ---- dados de demonstração --------------------------------------------------------
class ConfirmIn(BaseModel):
    confirm: str


@router.post("/admin/demo/load")
def demo_load(auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    res = seed.seed_demo(db)
    audit(db, auth.user, "demo.carregada", None, None, {"tickets": res["tickets"]}, auth.ip)
    db.commit()
    hub.publish("queue.updated", {})
    return res


@router.post("/admin/demo/clear")
def demo_clear(body: ConfirmIn, auth: Auth = Depends(require(CFG)), db: Session = Depends(get_db)):
    if body.confirm != "LIMPAR":
        raise HTTPException(422, "Digite LIMPAR para confirmar.")
    res = seed.remove_demo_data(db)
    audit(db, auth.user, "demo.removida", None, None, res, auth.ip)
    db.commit()
    hub.publish("queue.updated", {})
    return res
