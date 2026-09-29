"""Modelo de dados. Convenções: datas em UTC, chaves inteiras, FKs explícitas."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, UTCDateTime, utcnow

BigPK = BigInteger().with_variant(Integer, "sqlite")  # autoincrement no SQLite

# ---- Enumerações (armazenadas como texto + CHECK) ---------------------------
TICKET_STATUSES = (
    "AGUARDANDO",
    "CHAMADA",
    "RECHAMADA",
    "EM_ATENDIMENTO",
    "ATENDIDA",
    "NAO_COMPARECEU",
    "CANCELADA",
)
ACTIVE_STATUSES = ("CHAMADA", "RECHAMADA", "EM_ATENDIMENTO")
FINAL_STATUSES = ("ATENDIDA", "NAO_COMPARECEU", "CANCELADA")
PRINT_STATUSES = ("PENDENTE", "ENVIANDO", "IMPRESSO", "ERRO", "CANCELADO")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)


# ---- Usuários e permissões --------------------------------------------------
class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(255), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    permissions: Mapped[list[Permission]] = relationship(secondary="role_permissions", lazy="selectin")


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)  # sempre minúsculo
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    role: Mapped[Role] = relationship(lazy="joined")


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    computer_id: Mapped[int | None] = mapped_column(ForeignKey("computers.id", ondelete="SET NULL"))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


# ---- Estrutura física -------------------------------------------------------
class Computer(TimestampMixin, Base):
    __tablename__ = "computers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(255), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Counter(TimestampMixin, Base):
    """Guichê / posto de atendimento (ex.: COLETA 01)."""

    __tablename__ = "counters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    spoken_name: Mapped[str] = mapped_column(String(80), default="")  # como a voz deve falar
    position: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Lista de ticket_types.id que este guichê atende. NULL/[] = todos.
    accepted_type_ids: Mapped[list | None] = mapped_column(JSON)


class Attendant(Base):
    """Perfil operacional do usuário: qual guichê ele ocupa agora."""

    __tablename__ = "attendants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("counters.id", ondelete="SET NULL"), index=True)
    counter_since: Mapped[datetime | None] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Panel(TimestampMixin, Base):
    __tablename__ = "panels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    computer_id: Mapped[int | None] = mapped_column(ForeignKey("computers.id", ondelete="SET NULL"))
    history_size: Mapped[int] = mapped_column(Integer, default=6)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


# ---- Filas ------------------------------------------------------------------
class TicketType(TimestampMixin, Base):
    __tablename__ = "ticket_types"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(4), unique=True)
    color: Mapped[str] = mapped_column(String(9), default="#2563eb")
    position: Mapped[int] = mapped_column(Integer, default=0)
    # 0 = fila comum; >0 = prioritária (maior = mais urgente)
    priority_level: Mapped[int] = mapped_column(Integer, default=0)
    # Se verdadeiro, a recepção deve escolher uma categoria de prioridade
    requires_category: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Priority(TimestampMixin, Base):
    """Categoria de prioridade legal/institucional — 100% configurável."""

    __tablename__ = "priorities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(500), default="")
    legal_basis: Mapped[str] = mapped_column(String(500), default="")
    rank: Mapped[int] = mapped_column(Integer, default=100)  # menor = atendida antes
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TicketSequence(Base):
    """Contador de numeração. Incrementado atomicamente (UPDATE ... RETURNING)."""

    __tablename__ = "ticket_sequences"
    __table_args__ = (UniqueConstraint("ticket_type_id", "seq_date", name="uq_sequence_type_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_type_id: Mapped[int] = mapped_column(ForeignKey("ticket_types.id"))
    seq_date: Mapped[date] = mapped_column(Date)
    last_number: Mapped[int] = mapped_column(Integer, default=0)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("ticket_type_id", "seq_date", "number", name="uq_ticket_number"),
        CheckConstraint(_in("status", TICKET_STATUSES), name="ck_ticket_status"),
        Index("ix_tickets_queue", "status", "service_date", "created_at"),
        Index("ix_tickets_service_date", "service_date"),
        Index("ix_tickets_code_date", "service_date", "code"),
    )
    id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    code: Mapped[str] = mapped_column(String(20))
    number: Mapped[int] = mapped_column(Integer)
    ticket_type_id: Mapped[int] = mapped_column(ForeignKey("ticket_types.id"), index=True)
    priority_id: Mapped[int | None] = mapped_column(ForeignKey("priorities.id"))
    status: Mapped[str] = mapped_column(String(20), default="AGUARDANDO")
    service_date: Mapped[date] = mapped_column(Date)  # dia local do atendimento
    seq_date: Mapped[date] = mapped_column(Date)  # chave da numeração
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    computer_id: Mapped[int | None] = mapped_column(ForeignKey("computers.id", ondelete="SET NULL"))
    called_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # primeira chamada
    last_called_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    recall_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("counters.id"), index=True)
    attendant_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status_reason: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    ticket_type: Mapped[TicketType] = relationship(lazy="joined")
    priority: Mapped[Priority | None] = relationship(lazy="joined")
    counter: Mapped[Counter | None] = relationship(lazy="joined")
    attendant: Mapped[User | None] = relationship(foreign_keys=[attendant_id], lazy="joined")


class QueueEvent(Base):
    """Trilha imutável de todas as movimentações da senha."""

    __tablename__ = "queue_events"
    __table_args__ = (Index("ix_queue_events_ticket", "ticket_id", "created_at"),)
    id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    event_type: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("counters.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    details: Mapped[dict | None] = mapped_column(JSON)


# ---- Impressão --------------------------------------------------------------
class PrintAgent(TimestampMixin, Base):
    __tablename__ = "print_agents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    computer_id: Mapped[int | None] = mapped_column(ForeignKey("computers.id", ondelete="SET NULL"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    version: Mapped[str | None] = mapped_column(String(30))
    hostname: Mapped[str | None] = mapped_column(String(120))
    last_error: Mapped[str | None] = mapped_column(String(500))
    was_online: Mapped[bool] = mapped_column(Boolean, default=False)  # p/ detectar transições


class Printer(TimestampMixin, Base):
    __tablename__ = "printers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    connection: Mapped[str] = mapped_column(String(10), default="AGENT")  # AGENT | NETWORK
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("print_agents.id", ondelete="SET NULL"))
    system_name: Mapped[str] = mapped_column(String(120), default="")  # nome no Windows
    host: Mapped[str | None] = mapped_column(String(120))  # impressora de rede
    port: Mapped[int] = mapped_column(Integer, default=9100)
    paper_width_mm: Mapped[int] = mapped_column(Integer, default=80)
    chars_per_line: Mapped[int] = mapped_column(Integer, default=42)
    margin_top: Mapped[int] = mapped_column(Integer, default=1)  # linhas em branco
    margin_bottom: Mapped[int] = mapped_column(Integer, default=3)
    code_size: Mapped[int] = mapped_column(Integer, default=4)  # ampliação da senha 1..8
    cut: Mapped[bool] = mapped_column(Boolean, default=True)
    encoding: Mapped[str] = mapped_column(String(20), default="cp850")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="DESCONHECIDA")  # ONLINE|OFFLINE|SEM_PAPEL|ERRO
    status_detail: Mapped[str | None] = mapped_column(String(500))
    status_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_print_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    __table_args__ = (CheckConstraint("connection IN ('AGENT','NETWORK')", name="ck_printer_connection"),)


class PrintJob(Base):
    __tablename__ = "print_jobs"
    __table_args__ = (
        CheckConstraint(_in("status", PRINT_STATUSES), name="ck_print_status"),
        Index("ix_print_jobs_queue", "status", "printer_id", "id"),
    )
    id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), index=True)
    printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(10), default="TICKET")  # TICKET | TEST
    status: Mapped[str] = mapped_column(String(10), default="PENDENTE")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    printed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    ticket: Mapped[Ticket | None] = relationship(lazy="joined")
    printer: Mapped[Printer | None] = relationship(lazy="joined")


# ---- Configuração, auditoria, backup ---------------------------------------
class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[object] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_at", "created_at"),)
    id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    user_id: Mapped[int | None] = mapped_column(Integer)  # sem FK: log sobrevive ao usuário
    username: Mapped[str | None] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(40))
    details: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))


class Backup(Base):
    __tablename__ = "backups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(1000))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    kind: Mapped[str] = mapped_column(String(15), default="MANUAL")  # MANUAL|AUTO|PRE_RESTORE
    status: Mapped[str] = mapped_column(String(10), default="OK")  # OK|ERRO
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    restored_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
