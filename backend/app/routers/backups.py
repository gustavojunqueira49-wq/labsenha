from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Auth, require
from ..events import hub
from ..models import Backup
from ..serializers import dt
from ..services import backup as svc

router = APIRouter(prefix="/backups", tags=["Backup"])


def out(b: Backup) -> dict:
    return {"id": b.id, "filename": b.filename, "size_bytes": b.size_bytes, "kind": b.kind, "status": b.status,
            "error": b.error, "created_at": dt(b.created_at), "restored_at": dt(b.restored_at),
            "exists": b.status == "OK" and Path(b.path).exists()}


@router.get("")
def list_backups(auth: Auth = Depends(require("backup.manage")), db: Session = Depends(get_db)):
    return {"status": svc.status(db), "directory": str(svc.backup_dir(db)),
            "backups": [out(b) for b in db.scalars(select(Backup).order_by(Backup.id.desc()).limit(200))]}


@router.post("", status_code=201)
def create(auth: Auth = Depends(require("backup.manage")), db: Session = Depends(get_db)):
    b = svc.create_backup(db, "MANUAL", auth.user)
    audit(db, auth.user, "backup.manual", "backup", b.id, {"status": b.status}, auth.ip)
    db.commit()
    if b.status != "OK":
        raise HTTPException(500, f"Falha no backup: {b.error}")
    return out(b)


class RestoreIn(BaseModel):
    confirm: str


@router.post("/{backup_id}/restore")
def restore(backup_id: int, body: RestoreIn, auth: Auth = Depends(require("backup.manage")), db: Session = Depends(get_db)):
    if body.confirm != "RESTAURAR":
        raise HTTPException(422, "Digite RESTAURAR para confirmar.")
    b = db.get(Backup, backup_id)
    if b is None:
        raise HTTPException(404, "Backup não encontrado.")
    audit(db, auth.user, "backup.restauracao", "backup", b.id, None, auth.ip)
    db.commit()
    try:
        svc.restore(db, b, auth.user)
    except svc.BackupError as e:
        raise HTTPException(500, str(e)) from None
    hub.publish("system.restored", {})
    return {"ok": True, "message": "Backup restaurado. Todos os usuários precisam entrar novamente."}
