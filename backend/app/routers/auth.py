from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db, utcnow
from ..deps import Auth, client_ip, current_auth, current_auth_ready
from ..models import Attendant, Computer, Counter, User, UserSession
from ..security import hash_password, new_token, token_hash, validate_password_strength, verify_password
from ..serializers import counter_out, user_out
from ..services import settings_service

router = APIRouter(prefix="/auth", tags=["Autenticação"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


def me_payload(db: Session, auth: Auth) -> dict:
    att = db.scalars(select(Attendant).where(Attendant.user_id == auth.user.id)).first()
    counter = db.get(Counter, att.counter_id) if att and att.counter_id else None
    return {**user_out(auth.user), "permissions": sorted(auth.perms),
            "counter": counter_out(counter) if counter else None}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    username = body.username.strip().lower()
    user = db.scalars(select(User).where(User.username == username)).first()
    now = utcnow()
    st = settings_service.get_all(db)
    generic = HTTPException(401, "Usuário ou senha inválidos.")
    if user is None:
        audit(db, None, "login.falha", "user", None, {"username": username[:50]}, ip, username[:50])
        db.commit()
        raise generic
    if user.locked_until and user.locked_until > now:
        mins = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(423, f"Usuário bloqueado por tentativas inválidas. Tente em {mins} min.")
    if not user.active or not verify_password(body.password, user.password_hash):
        if user.active:
            user.failed_attempts += 1
            if user.failed_attempts >= int(st["security.max_failed_logins"]):
                user.locked_until = now + timedelta(minutes=int(st["security.lockout_minutes"]))
                user.failed_attempts = 0
                audit(db, user, "login.bloqueado", "user", user.id, None, ip)
        audit(db, user, "login.falha", "user", user.id, None, ip)
        db.commit()
        raise generic
    user.failed_attempts, user.locked_until, user.last_login_at = 0, None, now
    token = new_token()
    computer = db.scalars(select(Computer).where(Computer.ip_address == ip, Computer.active.is_(True))).first() if ip else None
    if computer:
        computer.last_seen_at = now
    db.add(UserSession(token_hash=token_hash(token), user_id=user.id, computer_id=computer.id if computer else None,
                       ip_address=ip, user_agent=(request.headers.get("user-agent") or "")[:255]))
    audit(db, user, "login", "user", user.id, {"computer": computer.name if computer else None}, ip)
    db.commit()
    auth = Auth(user=user, session=None, perms={p.code for p in user.role.permissions})  # type: ignore[arg-type]
    return {"token": token, "user": me_payload(db, auth), "settings": settings_service.public_view(st)}


@router.post("/logout")
def logout(auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    auth.session.revoked_at = utcnow()
    db.execute(update(Attendant).where(Attendant.user_id == auth.user.id).values(counter_id=None, counter_since=None))
    audit(db, auth.user, "logout", "user", auth.user.id, None, auth.ip)
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    return {"user": me_payload(db, auth), "settings": settings_service.public_view(settings_service.get_all(db))}


@router.post("/change-password")
def change_password(body: PasswordIn, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    u = auth.user
    if not verify_password(body.current_password, u.password_hash):
        raise HTTPException(400, "Senha atual incorreta.")
    if body.new_password == body.current_password:
        raise HTTPException(400, "A nova senha deve ser diferente da atual.")
    err = validate_password_strength(body.new_password, u.username)
    if err:
        raise HTTPException(422, err)
    u.password_hash = hash_password(body.new_password)
    u.must_change_password = False
    u.password_changed_at = utcnow()
    db.execute(update(UserSession).where(UserSession.user_id == u.id, UserSession.id != auth.session.id,
                                         UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    audit(db, u, "senha.alterada", "user", u.id, None, auth.ip)
    db.commit()
    return {"ok": True}


# ---- guichê do atendente ----------------------------------------------------
occupy_router = APIRouter(tags=["Guichês"])


def _session_alive(db: Session, user_id: int) -> bool:
    idle = int(settings_service.get(db, "session.idle_minutes"))
    s = db.scalars(select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
                   .order_by(UserSession.last_seen_at.desc())).first()
    return bool(s and utcnow() - s.last_seen_at <= timedelta(minutes=idle))


@occupy_router.post("/counters/{counter_id}/occupy")
def occupy(counter_id: int, auth: Auth = Depends(current_auth_ready), db: Session = Depends(get_db)):
    if not (auth.can("ticket.call")):
        raise HTTPException(403, "Sem permissão.")
    counter = db.get(Counter, counter_id)
    if counter is None or not counter.active:
        raise HTTPException(404, "Guichê inexistente ou inativo.")
    other = db.scalars(select(Attendant).where(Attendant.counter_id == counter_id, Attendant.user_id != auth.user.id)).first()
    if other and _session_alive(db, other.user_id) and not auth.can("ticket.override"):
        who = db.get(User, other.user_id)
        raise HTTPException(409, f"{counter.name} já está em uso por {who.full_name}.")
    if other:
        other.counter_id = None
    att = db.scalars(select(Attendant).where(Attendant.user_id == auth.user.id)).first()
    if att is None:
        att = Attendant(user_id=auth.user.id)
        db.add(att)
    att.counter_id, att.counter_since = counter_id, utcnow()
    audit(db, auth.user, "guiche.ocupado", "counter", counter_id, None, auth.ip)
    db.commit()
    return {"counter": counter_out(counter)}


@occupy_router.delete("/me/counter")
def release(auth: Auth = Depends(current_auth_ready), db: Session = Depends(get_db)):
    db.execute(update(Attendant).where(Attendant.user_id == auth.user.id).values(counter_id=None, counter_since=None))
    db.commit()
    return {"ok": True}
