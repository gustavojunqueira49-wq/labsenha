"""Backup/restauração. PostgreSQL: pg_dump/pg_restore. SQLite (dev): API de backup online."""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from .. import db as dbmod
from ..config import config
from ..db import utcnow
from ..models import Backup, User
from . import settings_service


class BackupError(Exception):
    pass


def backup_dir(db: Session) -> Path:
    custom = (settings_service.get(db, "backup.dir") or "").strip()
    p = Path(custom) if custom else config.backup_dir
    p.mkdir(parents=True, exist_ok=True)
    return p


def _pg_tool(name: str) -> str:
    if config.pg_bin_dir:
        exe = Path(config.pg_bin_dir) / (name + (".exe" if os.name == "nt" else ""))
        return str(exe)
    return shutil.which(name) or name


def _pg_env(url) -> dict:
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = url.password
    return env


def _pg_args(url) -> list[str]:
    a = ["-h", url.host or "localhost", "-p", str(url.port or 5432)]
    if url.username:
        a += ["-U", url.username]
    return a


def _run(cmd: list[str], env: dict) -> None:
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        raise BackupError(f"Ferramenta não encontrada: {cmd[0]}. Configure PG_BIN_DIR no .env.") from None
    if r.returncode != 0:
        raise BackupError((r.stderr or r.stdout or "erro desconhecido").strip()[:1000])


def create_backup(db: Session, kind: str = "MANUAL", user: User | None = None) -> Backup:
    stamp = utcnow().astimezone(config.tz).strftime("%Y%m%d_%H%M%S")
    url = make_url(config.database_url)
    ext = "sqlite" if config.is_sqlite else "dump"
    filename = f"backup_{stamp}_{kind.lower()}.{ext}"
    path = backup_dir(db) / filename
    rec = Backup(filename=filename, path=str(path), kind=kind, created_by=user.id if user else None)
    try:
        if config.is_sqlite:
            src = sqlite3.connect(url.database)
            dst = sqlite3.connect(path)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
        else:
            _run([_pg_tool("pg_dump"), *_pg_args(url), "-Fc", "-f", str(path), url.database], _pg_env(url))
        rec.size_bytes = path.stat().st_size
    except Exception as e:  # registra a falha (aparece no histórico e no alerta)
        rec.status, rec.error = "ERRO", str(e)[:1000]
        path.unlink(missing_ok=True)
    db.add(rec)
    db.commit()
    if rec.status == "OK" and kind == "AUTO":
        prune(db)
    return rec


def prune(db: Session) -> None:
    keep = int(settings_service.get(db, "backup.keep"))
    autos = list(db.scalars(select(Backup).where(Backup.kind == "AUTO", Backup.status == "OK").order_by(Backup.id.desc())))
    for old in autos[keep:]:
        Path(old.path).unlink(missing_ok=True)
        old.status, old.error = "ERRO", "Removido pela rotação de backups"
    db.commit()


def last_ok(db: Session) -> Backup | None:
    return db.scalars(select(Backup).where(Backup.status == "OK").order_by(Backup.created_at.desc())).first()


def status(db: Session) -> dict:
    last = last_ok(db)
    alert_h = int(settings_service.get(db, "backup.alert_hours"))
    age = (utcnow() - last.created_at) if last else None
    stale = last is None or age > timedelta(hours=alert_h)
    return {"last_backup_at": last.created_at.isoformat() if last else None,
            "age_hours": round(age.total_seconds() / 3600, 1) if age else None,
            "stale": stale, "alert_hours": alert_h,
            "message": ("Nenhum backup realizado ainda." if last is None else
                        f"Último backup há {round(age.total_seconds() / 3600)} h — acima do limite de {alert_h} h."
                        if stale else None)}


def due_for_auto(db: Session) -> bool:
    if not settings_service.get(db, "backup.auto_enabled"):
        return False
    last = db.scalars(select(Backup).order_by(Backup.created_at.desc())).first()  # inclui falhas: evita loop
    interval = timedelta(hours=int(settings_service.get(db, "backup.interval_hours")))
    return last is None or utcnow() - last.created_at >= interval


def restore(db: Session, backup: Backup, user: User | None) -> None:
    """Restaura o backup. Antes, faz um backup de segurança (PRE_RESTORE)."""
    path = Path(backup.path)
    if backup.status != "OK" or not path.exists():
        raise BackupError("Arquivo de backup não encontrado.")
    safety = create_backup(db, "PRE_RESTORE", user)
    if safety.status != "OK":
        raise BackupError(f"Não foi possível criar o backup de segurança: {safety.error}")
    url = make_url(config.database_url)
    backup_id = backup.id
    db.close()
    dbmod.engine.dispose()
    if config.is_sqlite:
        for suffix in ("-wal", "-shm"):
            Path(str(url.database) + suffix).unlink(missing_ok=True)
        shutil.copyfile(path, url.database)
    else:
        _run([_pg_tool("pg_restore"), *_pg_args(url), "--clean", "--if-exists", "--no-owner", "-d", url.database,
              str(path)], _pg_env(url))
    with dbmod.SessionLocal() as s2:
        rec = s2.get(Backup, backup_id)
        if rec is not None:
            rec.restored_at = utcnow()
            s2.commit()
