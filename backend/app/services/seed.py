"""Dados iniciais (idempotente) e ambiente de demonstração."""
from __future__ import annotations

import os
import random
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import config
from ..db import utcnow
from ..deps import ALL_PERMISSIONS, DEFAULT_ROLES
from ..models import (Attendant, Computer, Counter, Panel, Permission, PrintAgent, PrintJob, Printer, Priority,
                      QueueEvent, Role, Ticket, TicketSequence, TicketType, User)
from ..security import hash_password, random_password

LEGAL_NOTE = "SUGESTÃO INICIAL — validar com a assessoria jurídica do hospital. "

DEFAULT_TYPES = [
    # code, name, prefix, color, position, level, requires_category, active
    ("NORMAL", "Atendimento Normal", "N", "#2563eb", 1, 0, False, True),
    ("PRIORIDADE", "Atendimento Prioritário", "P", "#dc2626", 2, 1, True, True),
    ("AGENDADO", "Coleta Agendada", "A", "#059669", 3, 0, False, True),
    ("OUTROS", "Outros", "O", "#7c3aed", 4, 0, False, True),
    ("URGENCIA", "Urgência", "U", "#ea580c", 5, 5, False, False),
]
# code, name, description, legal_basis, rank
DEFAULT_PRIORITIES = [
    ("IDOSO_80", "Pessoa idosa (80+ anos)", "Prioridade especial",
     LEGAL_NOTE + "Estatuto da Pessoa Idosa (Lei 10.741/2003), art. 3º, §2º.", 1),
    ("IDOSO", "Pessoa idosa (60+ anos)", "", LEGAL_NOTE + "Lei 10.048/2000; Lei 10.741/2003, art. 3º.", 2),
    ("PCD", "Pessoa com deficiência", "", LEGAL_NOTE + "Lei 10.048/2000; Lei 13.146/2015 (LBI).", 3),
    ("TEA", "Pessoa com transtorno do espectro autista", "", LEGAL_NOTE + "Lei 10.048/2000 (redação da Lei 14.626/2023).", 4),
    ("GESTANTE", "Gestante", "", LEGAL_NOTE + "Lei 10.048/2000.", 5),
    ("LACTANTE", "Lactante", "", LEGAL_NOTE + "Lei 10.048/2000.", 6),
    ("CRIANCA_COLO", "Pessoa com criança de colo", "", LEGAL_NOTE + "Lei 10.048/2000.", 7),
    ("MOBILIDADE", "Pessoa com mobilidade reduzida", "", LEGAL_NOTE + "Lei 10.048/2000 (redação da Lei 14.626/2023).", 8),
    ("OBESO", "Pessoa obesa", "", LEGAL_NOTE + "Lei 10.048/2000.", 9),
    ("INSTITUCIONAL", "Prioridade institucional", "Definida pela política interna do hospital",
     "Política interna do hospital (descrever a norma/portaria).", 50),
]


def seed_base(db: Session) -> str | None:
    """Cria papéis, permissões, tipos, prioridades, guichês e o administrador inicial.
    Retorna a senha temporária gerada (ou None se o admin já existia)."""
    perms = {p.code: p for p in db.scalars(select(Permission))}
    for code, desc in ALL_PERMISSIONS.items():
        if code not in perms:
            perms[code] = Permission(code=code, description=desc)
            db.add(perms[code])
    db.flush()
    roles = {r.code: r for r in db.scalars(select(Role))}
    for code, (name, plist) in DEFAULT_ROLES.items():
        if code not in roles:
            roles[code] = Role(code=code, name=name, permissions=[perms[p] for p in plist])
            db.add(roles[code])
    admin_role = roles["ADMINISTRADOR"]
    admin_role.permissions = list(perms.values())  # administrador sempre tem tudo
    db.flush()

    if db.scalar(select(TicketType.id).limit(1)) is None:
        for code, name, prefix, color, pos, level, req, active in DEFAULT_TYPES:
            db.add(TicketType(code=code, name=name, prefix=prefix, color=color, position=pos,
                              priority_level=level, requires_category=req, active=active))
    if db.scalar(select(Priority.id).limit(1)) is None:
        for code, name, desc, basis, rank in DEFAULT_PRIORITIES:
            db.add(Priority(code=code, name=name, description=desc, legal_basis=basis, rank=rank))
    if db.scalar(select(Counter.id).limit(1)) is None:
        for i in (1, 2):
            db.add(Counter(code=f"COLETA{i:02d}", name=f"COLETA {i:02d}", spoken_name=f"coleta {i}", position=i))
    if db.scalar(select(Panel.id).limit(1)) is None:
        db.add(Panel(code="PAINEL01", name="Painel principal"))

    temp = None
    if db.scalar(select(User.id).where(User.role_id == admin_role.id).limit(1)) is None:
        temp = config.initial_admin_password or random_password()
        db.add(User(username=config.initial_admin_username.lower(), full_name="Administrador",
                    password_hash=hash_password(temp), role_id=admin_role.id,
                    must_change_password=True))
    db.commit()
    return temp


def write_first_access_file(username: str, password: str) -> Path:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    path = config.data_dir / "PRIMEIRO_ACESSO.txt"
    path.write_text(
        f"Usuário: {username}\nSenha temporária: {password}\n\n"
        "A senha deverá ser trocada no primeiro acesso. APAGUE este arquivo depois.\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


DEMO_USERS = [
    ("recepcao", "Rita Recepção", "RECEPCAO"), ("maria", "Maria Coleta", "ATENDENTE"),
    ("joao", "João Coleta", "ATENDENTE"), ("painel", "Painel TV", "PAINEL"),
    ("supervisor", "Sara Supervisão", "SUPERVISAO"),
]
DEMO_PASSWORD = "Demo@12345"


def seed_demo(db: Session) -> dict:
    """5 usuários, 4 guichês, 1 painel, 1 impressora e 20 senhas (marcadas como demonstração via usuário 'recepcao')."""
    from . import printing, queue as q  # evitar import circular

    roles = {r.code: r for r in db.scalars(select(Role))}
    for username, name, role in DEMO_USERS:
        if db.scalar(select(User).where(User.username == username)) is None:
            db.add(User(username=username, full_name=name, password_hash=hash_password(DEMO_PASSWORD),
                        role_id=roles[role].id, must_change_password=False))
    for i in range(1, 5):
        if db.scalar(select(Counter).where(Counter.code == f"COLETA{i:02d}")) is None:
            db.add(Counter(code=f"COLETA{i:02d}", name=f"COLETA {i:02d}", spoken_name=f"coleta {i}", position=i))
    comp = db.scalar(select(Computer).where(Computer.name == "PC-RECEPCAO"))
    if comp is None:
        comp = Computer(name="PC-RECEPCAO", ip_address="192.168.1.101", description="Recepção (demo)")
        db.add(comp)
        db.flush()
    agent = db.scalar(select(PrintAgent).where(PrintAgent.name == "Agente Recepção (demo)"))
    if agent is None:
        _, h = printing.new_agent_token()
        agent = PrintAgent(name="Agente Recepção (demo)", token_hash=h, computer_id=comp.id)
        db.add(agent)
        db.flush()
    if db.scalar(select(Printer).where(Printer.name == "EPSON TM-T20 (demo)")) is None:
        db.add(Printer(name="EPSON TM-T20 (demo)", agent_id=agent.id, system_name="EPSON TM-T20",
                       is_default=True, chars_per_line=42))
    db.flush()
    rec = db.scalar(select(User).where(User.username == "recepcao"))
    types = {t.code: t for t in db.scalars(select(TicketType))}
    cats = list(db.scalars(select(Priority).where(Priority.active.is_(True)).order_by(Priority.rank)))
    rnd = random.Random(7)
    made = []
    for i in range(20):
        code = rnd.choice(["NORMAL", "NORMAL", "NORMAL", "PRIORIDADE", "AGENDADO", "OUTROS"])
        t = types[code]
        made.append(q.issue_ticket(db, t.id, rnd.choice(cats).id if t.requires_category else None, rec))
        printing.create_ticket_job(db, made[-1], rec)
    # espalha os horários de chegada nos últimos 40 min
    for n, t in enumerate(made):
        t.created_at = utcnow() - timedelta(minutes=40 - 2 * n)
    db.commit()
    return {"users": len(DEMO_USERS), "tickets": len(made), "demo_password": DEMO_PASSWORD}


def clear_operational_data(db: Session) -> dict:
    """Limpa senhas, eventos, impressões e numeração (mantém usuários/configurações). Uso: antes da produção."""
    n = db.query(Ticket).count()
    for model in (PrintJob, QueueEvent, TicketSequence, Ticket):
        db.execute(delete(model))
    db.execute(Attendant.__table__.update().values(counter_id=None, counter_since=None))
    db.commit()
    return {"tickets_removed": n}


def remove_demo_data(db: Session) -> dict:
    """Remove usuários/estruturas de demonstração e todos os dados operacionais."""
    res = clear_operational_data(db)
    names = [u[0] for u in DEMO_USERS]
    for u in db.scalars(select(User).where(User.username.in_(names))):
        db.execute(Attendant.__table__.delete().where(Attendant.user_id == u.id))
        db.delete(u)
    for model, col, val in ((Printer, Printer.name, "EPSON TM-T20 (demo)"),
                            (PrintAgent, PrintAgent.name, "Agente Recepção (demo)"),
                            (Computer, Computer.name, "PC-RECEPCAO")):
        db.execute(delete(model).where(col == val))
    db.commit()
    return res
