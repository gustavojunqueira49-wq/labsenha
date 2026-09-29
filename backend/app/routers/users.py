from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db, utcnow
from ..deps import ALL_PERMISSIONS, Auth, require
from ..models import Permission, Role, User, UserSession
from ..security import hash_password, validate_password_strength
from ..serializers import user_out

router = APIRouter(tags=["Usuários"])
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,50}$")


class UserIn(BaseModel):
    username: str = Field(max_length=50)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(max_length=200)
    role: str = Field(max_length=30)
    must_change_password: bool = True

    @field_validator("username")
    @classmethod
    def _u(cls, v: str) -> str:
        v = v.strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError("Usuário: 3–50 caracteres (letras minúsculas, números, . _ -)")
        return v


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=200)
    must_change_password: bool | None = None
    unlock: bool | None = None


def _role(db: Session, code: str) -> Role:
    r = db.scalars(select(Role).where(Role.code == code)).first()
    if r is None:
        raise HTTPException(422, "Perfil inexistente.")
    return r


def _admins_left(db: Session, excluding: int) -> int:
    admin = _role(db, "ADMINISTRADOR")
    return len(list(db.scalars(select(User.id).where(User.role_id == admin.id, User.active.is_(True), User.id != excluding))))


@router.get("/users")
def list_users(auth: Auth = Depends(require("users.manage")), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.full_name))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, auth: Auth = Depends(require("users.manage")), db: Session = Depends(get_db)):
    if db.scalars(select(User).where(User.username == body.username)).first():
        raise HTTPException(409, "Já existe um usuário com esse login.")
    err = validate_password_strength(body.password, body.username)
    if err:
        raise HTTPException(422, err)
    role = _role(db, body.role)
    u = User(username=body.username, full_name=body.full_name.strip(), password_hash=hash_password(body.password),
             role_id=role.id, must_change_password=body.must_change_password)
    db.add(u)
    db.flush()
    audit(db, auth.user, "usuario.criado", "user", u.id, {"username": u.username, "role": role.code}, auth.ip)
    db.commit()
    db.refresh(u)
    return user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, auth: Auth = Depends(require("users.manage")), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "Usuário não encontrado.")
    changes: dict = {}
    if body.full_name is not None:
        u.full_name = body.full_name.strip()
        changes["full_name"] = u.full_name
    if body.role is not None and body.role != u.role.code:
        role = _role(db, body.role)
        if u.role.code == "ADMINISTRADOR" and _admins_left(db, u.id) == 0:
            raise HTTPException(409, "Deve existir ao menos um administrador ativo.")
        u.role_id, changes["role"] = role.id, role.code
        u.role = role
    if body.active is not None and body.active != u.active:
        if not body.active:
            if u.id == auth.user.id:
                raise HTTPException(409, "Você não pode bloquear a si mesmo.")
            if u.role.code == "ADMINISTRADOR" and _admins_left(db, u.id) == 0:
                raise HTTPException(409, "Deve existir ao menos um administrador ativo.")
            db.execute(update(UserSession).where(UserSession.user_id == u.id, UserSession.revoked_at.is_(None))
                       .values(revoked_at=utcnow()))
        u.active = body.active
        changes["active"] = body.active
    if body.password:
        err = validate_password_strength(body.password, u.username)
        if err:
            raise HTTPException(422, err)
        u.password_hash = hash_password(body.password)
        u.must_change_password = True if body.must_change_password is None else body.must_change_password
        db.execute(update(UserSession).where(UserSession.user_id == u.id, UserSession.revoked_at.is_(None))
                   .values(revoked_at=utcnow()))
        changes["password"] = "redefinida"
    elif body.must_change_password is not None:
        u.must_change_password = body.must_change_password
    if body.unlock:
        u.locked_until, u.failed_attempts = None, 0
        changes["unlock"] = True
    audit(db, auth.user, "usuario.alterado", "user", u.id, changes, auth.ip)
    db.commit()
    return user_out(u)


@router.get("/roles")
def list_roles(auth: Auth = Depends(require("users.manage")), db: Session = Depends(get_db)):
    return {
        "roles": [{"code": r.code, "name": r.name, "permissions": sorted(p.code for p in r.permissions)}
                  for r in db.scalars(select(Role).order_by(Role.id))],
        "permissions": [{"code": c, "description": d} for c, d in ALL_PERMISSIONS.items()],
    }


class RolePerms(BaseModel):
    permissions: list[str]


@router.put("/roles/{code}/permissions")
def set_permissions(code: str, body: RolePerms, auth: Auth = Depends(require("users.manage")), db: Session = Depends(get_db)):
    role = _role(db, code)
    if role.code == "ADMINISTRADOR":
        raise HTTPException(409, "O perfil Administrador sempre possui todas as permissões.")
    perms = list(db.scalars(select(Permission).where(Permission.code.in_(body.permissions))))
    if len(perms) != len(set(body.permissions)):
        raise HTTPException(422, "Permissão desconhecida.")
    role.permissions = perms
    audit(db, auth.user, "perfil.permissoes", "role", role.code, {"permissions": sorted(body.permissions)}, auth.ip)
    db.commit()
    return {"code": role.code, "permissions": sorted(p.code for p in role.permissions)}
