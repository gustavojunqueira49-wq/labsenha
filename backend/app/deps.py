from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, utcnow
from .models import PrintAgent, User, UserSession
from .security import token_hash
from .services import settings_service

ALL_PERMISSIONS: dict[str, str] = {
    "ticket.create": "Emitir senhas (recepção)",
    "ticket.view": "Visualizar filas e senhas",
    "ticket.call": "Chamar/atender senhas",
    "ticket.override": "Operar senhas de outros atendentes",
    "ticket.cancel": "Cancelar senhas",
    "panel.view": "Exibir o painel de chamadas",
    "dashboard.view": "Ver o dashboard",
    "reports.view": "Ver relatórios",
    "reports.export": "Exportar relatórios",
    "history.view": "Consultar histórico de senhas",
    "users.manage": "Gerenciar usuários e permissões",
    "config.manage": "Configurar sistema, filas, prioridades, guichês, computadores",
    "print.view": "Ver status da impressão",
    "print.manage": "Gerenciar impressoras/agentes e testar impressão",
    "print.reprint": "Reimprimir senhas",
    "backup.manage": "Backup e restauração",
    "audit.view": "Consultar logs de auditoria",
}

DEFAULT_ROLES: dict[str, tuple[str, list[str]]] = {
    "ADMINISTRADOR": ("Administrador", list(ALL_PERMISSIONS)),
    "RECEPCAO": ("Recepção", ["ticket.create", "ticket.view", "ticket.cancel", "print.view", "print.reprint"]),
    "ATENDENTE": ("Atendente", ["ticket.view", "ticket.call"]),
    "PAINEL": ("Painel", ["panel.view"]),
    "SUPERVISAO": ("Supervisão", ["ticket.view", "ticket.override", "ticket.cancel", "dashboard.view", "reports.view",
                                  "reports.export", "history.view", "audit.view", "print.view"]),
}


@dataclass
class Auth:
    user: User
    session: UserSession
    perms: set[str] = field(default_factory=set)
    ip: str | None = None

    def can(self, perm: str) -> bool:
        return perm in self.perms


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _token_from(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return None


def authenticate(db: Session, token: str | None) -> tuple[User, UserSession]:
    if not token:
        raise HTTPException(401, "Não autenticado.")
    sess = db.scalars(select(UserSession).where(UserSession.token_hash == token_hash(token))).first()
    if sess is None or sess.revoked_at is not None:
        raise HTTPException(401, "Sessão inválida. Faça login novamente.")
    user = db.get(User, sess.user_id)
    if user is None or not user.active:
        raise HTTPException(401, "Usuário inativo.")
    now = utcnow()
    if user.role.code != "PAINEL":
        idle = int(settings_service.get(db, "session.idle_minutes"))
        if now - sess.last_seen_at > timedelta(minutes=idle):
            sess.revoked_at = now
            db.commit()
            raise HTTPException(401, "Sessão expirada por inatividade.")
    if now - sess.last_seen_at > timedelta(seconds=30):
        sess.last_seen_at = now
        db.commit()
    return user, sess


def current_auth(request: Request, db: Session = Depends(get_db)) -> Auth:
    user, sess = authenticate(db, _token_from(request))
    return Auth(user=user, session=sess, perms={p.code for p in user.role.permissions}, ip=client_ip(request))


def current_auth_ready(auth: Auth = Depends(current_auth)) -> Auth:
    """Como current_auth, mas bloqueia quem ainda precisa trocar a senha."""
    if auth.user.must_change_password:
        raise HTTPException(403, "É necessário trocar a senha antes de continuar.")
    return auth


def require(*perms: str):
    def dep(auth: Auth = Depends(current_auth_ready)) -> Auth:
        if perms and not any(auth.can(p) for p in perms):
            raise HTTPException(403, "Sem permissão para esta operação.")
        return auth

    return dep


def current_agent(request: Request, db: Session = Depends(get_db)) -> PrintAgent:
    token = request.headers.get("x-agent-token", "")
    agent = db.scalars(select(PrintAgent).where(PrintAgent.token_hash == token_hash(token))).first() if token else None
    if agent is None or not agent.active:
        raise HTTPException(401, "Token do agente inválido.")
    return agent
