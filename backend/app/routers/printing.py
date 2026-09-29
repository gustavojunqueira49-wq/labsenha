from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db, utcnow
from ..deps import Auth, current_agent, require
from ..events import hub
from ..models import Computer, PrintAgent, PrintJob, Printer
from ..serializers import dt, job_out
from ..services import escpos, printing, settings_service

router = APIRouter(prefix="/print", tags=["Impressão"])
agent_router = APIRouter(prefix="/agent", tags=["Agente de impressão"])


def printer_out(p: Printer) -> dict:
    return {"id": p.id, "name": p.name, "connection": p.connection, "agent_id": p.agent_id,
            "system_name": p.system_name, "host": p.host, "port": p.port, "paper_width_mm": p.paper_width_mm,
            "chars_per_line": p.chars_per_line, "margin_top": p.margin_top, "margin_bottom": p.margin_bottom,
            "code_size": p.code_size, "cut": p.cut, "encoding": p.encoding, "is_default": p.is_default,
            "active": p.active, "status": p.status, "status_detail": p.status_detail,
            "status_at": dt(p.status_at), "last_print_at": dt(p.last_print_at)}


# ---- status -------------------------------------------------------------------
@router.get("/status")
def status(auth: Auth = Depends(require("print.view", "print.manage")), db: Session = Depends(get_db)):
    agents = printing.agents_overview(db)
    computers = {c.id: c.name for c in db.scalars(select(Computer))}
    for a in agents:
        a["computer"] = computers.get(a["computer_id"])
    printers = []
    for p in db.scalars(select(Printer).order_by(Printer.id)):
        d = printer_out(p)
        agent = next((a for a in agents if a["id"] == p.agent_id), None)
        d["agent_online"] = agent["online"] if agent else (p.connection == "NETWORK")
        d["pending_jobs"] = db.query(PrintJob).filter(PrintJob.printer_id == p.id,
                                                      PrintJob.status.in_(("PENDENTE", "ENVIANDO"))).count()
        printers.append(d)
    unassigned = db.query(PrintJob).filter(PrintJob.printer_id.is_(None), PrintJob.status == "PENDENTE").count()
    return {"agents": agents, "printers": printers, "queue": printing.queue_counts(db), "unassigned_jobs": unassigned}


@router.get("/jobs")
def jobs(status: str | None = None, limit: int = Query(100, ge=1, le=500),
         auth: Auth = Depends(require("print.view", "print.manage")), db: Session = Depends(get_db)):
    q = select(PrintJob).order_by(PrintJob.id.desc()).limit(limit)
    if status:
        q = q.where(PrintJob.status == status.upper())
    return [job_out(j) for j in db.scalars(q).unique()]


class RetryIn(BaseModel):
    printer_id: int | None = None


@router.post("/jobs/{job_id}/retry")
def retry(job_id: int, body: RetryIn, auth: Auth = Depends(require("print.manage", "print.reprint")),
          db: Session = Depends(get_db)):
    job = db.get(PrintJob, job_id)
    if job is None:
        raise HTTPException(404, "Trabalho de impressão não encontrado.")
    printing.retry_job(db, job, body.printer_id)
    audit(db, auth.user, "impressao.reenviada", "print_job", job.id, None, auth.ip)
    db.commit()
    hub.publish("print.job", {"job_id": job.id, "status": job.status})
    return job_out(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    job = db.get(PrintJob, job_id)
    if job is None or job.status == "IMPRESSO":
        raise HTTPException(404, "Trabalho não encontrado ou já impresso.")
    job.status = "CANCELADO"
    audit(db, auth.user, "impressao.cancelada", "print_job", job.id, None, auth.ip)
    db.commit()
    return job_out(job)


@router.post("/jobs/retry-all")
def retry_all(auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    n = 0
    for job in db.scalars(select(PrintJob).where(PrintJob.status == "ERRO")).unique():
        printing.retry_job(db, job)
        n += 1
    printing.assign_orphans(db)
    audit(db, auth.user, "impressao.reenvio_em_massa", "print_job", None, {"n": n}, auth.ip)
    db.commit()
    return {"requeued": n}


class TestIn(BaseModel):
    printer_id: int | None = None


@router.post("/test")
def test_print(body: TestIn, auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    printer = db.get(Printer, body.printer_id) if body.printer_id else printing.default_printer(db)
    if printer is None:
        raise HTTPException(404, "Nenhuma impressora cadastrada.")
    job = printing.create_test_job(db, printer, auth.user)
    audit(db, auth.user, "impressao.teste", "printer", printer.id, None, auth.ip)
    db.commit()
    hub.publish("print.job", {"job_id": job.id, "status": job.status})
    return job_out(job)


# ---- impressoras ---------------------------------------------------------------
class PrinterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    connection: str = Field(default="AGENT", pattern="^(AGENT|NETWORK)$")
    agent_id: int | None = None
    system_name: str = Field(default="", max_length=120)
    host: str | None = Field(default=None, max_length=120)
    port: int = Field(default=9100, ge=1, le=65535)
    paper_width_mm: int = Field(default=80, ge=40, le=120)
    chars_per_line: int = Field(default=42, ge=16, le=80)
    margin_top: int = Field(default=1, ge=0, le=10)
    margin_bottom: int = Field(default=3, ge=0, le=15)
    code_size: int = Field(default=4, ge=1, le=8)
    cut: bool = True
    encoding: str = Field(default="cp850", pattern="^(cp437|cp850|cp858|cp860|cp1252)$")
    is_default: bool = False
    active: bool = True


def _save_printer(db: Session, p: Printer, body: PrinterIn) -> None:
    if body.connection == "NETWORK" and not body.host:
        raise HTTPException(422, "Informe o endereço (IP) da impressora de rede.")
    if body.connection == "AGENT" and body.agent_id and db.get(PrintAgent, body.agent_id) is None:
        raise HTTPException(422, "Agente inexistente.")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    if body.is_default:
        for other in db.scalars(select(Printer).where(Printer.id != (p.id or 0), Printer.is_default.is_(True))):
            other.is_default = False


@router.get("/printers")
def list_printers(auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    return [printer_out(p) for p in db.scalars(select(Printer).order_by(Printer.id))]


@router.post("/printers", status_code=201)
def create_printer(body: PrinterIn, auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    p = Printer(name=body.name)
    _save_printer(db, p, body)
    if db.scalar(select(Printer.id).limit(1)) is None:
        p.is_default = True
    db.add(p)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe uma impressora com esse nome.") from None
    printing.assign_orphans(db)  # senhas que esperavam por uma impressora
    audit(db, auth.user, "impressora.criada", "printer", p.id, body.model_dump(), auth.ip)
    db.commit()
    return printer_out(p)


@router.put("/printers/{pid}")
def update_printer(pid: int, body: PrinterIn, auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    p = db.get(Printer, pid)
    if p is None:
        raise HTTPException(404, "Impressora não encontrada.")
    _save_printer(db, p, body)
    printing.assign_orphans(db)
    audit(db, auth.user, "impressora.alterada", "printer", p.id, body.model_dump(), auth.ip)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe uma impressora com esse nome.") from None
    return printer_out(p)


@router.get("/printers/{pid}/preview")
def preview(pid: int, auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    p = db.get(Printer, pid)
    if p is None:
        raise HTTPException(404, "Impressora não encontrada.")
    st = settings_service.get_all(db)
    lines = escpos.build_lines({"kind": "TICKET", "code": "P001", "type_name": "Atendimento Prioritário",
                                "category_name": "Prioridade", "issued_at": utcnow().isoformat()}, st)
    return {"text": escpos.render_text(lines, p.chars_per_line)}


# ---- agentes -------------------------------------------------------------------
class AgentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    computer_id: int | None = None
    active: bool = True


@router.get("/agents")
def list_agents(auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    return printing.agents_overview(db)


@router.post("/agents", status_code=201)
def create_agent(body: AgentIn, auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    token, h = printing.new_agent_token()
    a = PrintAgent(name=body.name, token_hash=h, computer_id=body.computer_id, active=body.active)
    db.add(a)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe um agente com esse nome.") from None
    audit(db, auth.user, "agente.criado", "print_agent", a.id, {"name": a.name}, auth.ip)
    db.commit()
    return {"id": a.id, "name": a.name, "token": token,
            "notice": "Guarde este token no config.ini do agente. Ele não será exibido novamente."}


@router.put("/agents/{aid}")
def update_agent(aid: int, body: AgentIn, auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    a = db.get(PrintAgent, aid)
    if a is None:
        raise HTTPException(404, "Agente não encontrado.")
    a.name, a.computer_id, a.active = body.name, body.computer_id, body.active
    audit(db, auth.user, "agente.alterado", "print_agent", a.id, body.model_dump(), auth.ip)
    db.commit()
    return {"ok": True}


@router.post("/agents/{aid}/rotate-token")
def rotate_token(aid: int, auth: Auth = Depends(require("print.manage")), db: Session = Depends(get_db)):
    a = db.get(PrintAgent, aid)
    if a is None:
        raise HTTPException(404, "Agente não encontrado.")
    token, a.token_hash = printing.new_agent_token()
    audit(db, auth.user, "agente.token_renovado", "print_agent", a.id, None, auth.ip)
    db.commit()
    return {"token": token}


# ---- API usada pelo agente -----------------------------------------------------------
class HeartbeatIn(BaseModel):
    version: str | None = None
    hostname: str | None = None
    printer_name: str | None = None
    printer_status: str | None = Field(default=None, pattern="^(ONLINE|OFFLINE|SEM_PAPEL|ERRO)$")
    printer_detail: str | None = Field(default=None, max_length=500)


@agent_router.post("/heartbeat")
def heartbeat(body: HeartbeatIn, agent: PrintAgent = Depends(current_agent), db: Session = Depends(get_db)):
    events = printing.heartbeat(db, agent, body.model_dump())
    db.commit()
    for e in set(events):
        hub.publish(e, {"agent_id": agent.id})
    return {"ok": True, "server_time": utcnow().isoformat()}


@agent_router.post("/jobs/claim")
def claim(body: HeartbeatIn, limit: int = Query(5, ge=1, le=20), agent: PrintAgent = Depends(current_agent),
          db: Session = Depends(get_db)):
    """Poll do agente: também serve de heartbeat. Só entrega jobs se a impressora não está reportando falha."""
    events = printing.heartbeat(db, agent, body.model_dump())
    jobs_ = [] if body.printer_status and body.printer_status != "ONLINE" else printing.claim_for_agent(db, agent, limit)
    db.commit()
    for e in set(events):
        hub.publish(e, {"agent_id": agent.id})
    return {"jobs": jobs_}


class ResultIn(BaseModel):
    ok: bool
    error: str | None = Field(default=None, max_length=500)
    printer_status: str | None = Field(default=None, pattern="^(ONLINE|OFFLINE|SEM_PAPEL|ERRO)$")


@agent_router.post("/jobs/{job_id}/result")
def result(job_id: int, body: ResultIn, agent: PrintAgent = Depends(current_agent), db: Session = Depends(get_db)):
    ids = {p.id for p in db.scalars(select(Printer).where(Printer.agent_id == agent.id))}
    try:
        job = printing.report_result(db, ids, job_id, body.ok, body.error, body.printer_status)
    except LookupError:
        raise HTTPException(404, "Trabalho não pertence a este agente.") from None
    db.commit()
    hub.publish("print.job", {"job_id": job.id, "status": job.status, "code": (job.payload or {}).get("code")})
    if not body.ok:
        hub.publish("printer.status", {"printer_id": job.printer_id, "status": body.printer_status or "ERRO"})
    return {"status": job.status}
