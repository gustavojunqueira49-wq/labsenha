"""Utilitário de linha de comando: python -m app.cli <comando>"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import select


def cmd_migrate(_):
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "migrations"))
    command.upgrade(cfg, "head")
    print("Banco atualizado.")


def _ensure_schema():
    """SQLite (demonstração) não passa pelo script de instalação: cria a estrutura via migração."""
    from sqlalchemy import inspect

    from . import db as dbmod

    if "roles" not in inspect(dbmod.engine).get_table_names():
        cmd_migrate(None)


def cmd_seed(_):
    _ensure_schema()
    from .config import config
    from .db import SessionLocal
    from .services import seed

    with SessionLocal() as db:
        temp = seed.seed_base(db)
    if temp:
        path = seed.write_first_access_file(config.initial_admin_username, temp)
        print(f"Administrador criado. Senha temporária gravada em: {path}")
    else:
        print("Dados básicos já existentes.")


def cmd_demo(_):
    _ensure_schema()
    from .db import SessionLocal
    from .services import seed

    with SessionLocal() as db:
        seed.seed_base(db)
        print(seed.seed_demo(db))


def cmd_clear(args):
    from .db import SessionLocal
    from .services import seed

    if input("Isso APAGA todas as senhas/impressões e remove usuários de demonstração. Digite LIMPAR: ") != "LIMPAR":
        sys.exit("Cancelado.")
    with SessionLocal() as db:
        print(seed.remove_demo_data(db))


def cmd_backup(_):
    from .db import SessionLocal
    from .services import backup

    with SessionLocal() as db:
        rec = backup.create_backup(db, "MANUAL")
    print(f"{rec.status}: {rec.path}" + (f" — {rec.error}" if rec.error else ""))
    sys.exit(0 if rec.status == "OK" else 1)


def cmd_restore(args):
    from .db import SessionLocal
    from .models import Backup
    from .services import backup

    with SessionLocal() as db:
        rec = db.scalars(select(Backup).where(Backup.path == str(Path(args.file).resolve()))).first()
        if rec is None:  # arquivo fora do histórico: registra para restaurar
            p = Path(args.file).resolve()
            rec = Backup(filename=p.name, path=str(p), size_bytes=p.stat().st_size, kind="MANUAL")
            db.add(rec)
            db.commit()
        if input("Isso SUBSTITUI os dados atuais. Digite RESTAURAR: ") != "RESTAURAR":
            sys.exit("Cancelado.")
        backup.restore(db, rec, None)
    print("Restauração concluída.")


def cmd_reset_admin(args):
    from .config import config
    from .db import SessionLocal
    from .models import User
    from .security import hash_password, random_password, validate_password_strength

    username = (args.username or config.initial_admin_username).lower()
    pw = getpass.getpass("Nova senha (vazio = gerar aleatória): ") or random_password()
    err = validate_password_strength(pw, username)
    if err:
        sys.exit(err)
    with SessionLocal() as db:
        u = db.scalars(select(User).where(User.username == username)).first()
        if u is None:
            sys.exit("Usuário não encontrado.")
        u.password_hash, u.must_change_password, u.active, u.locked_until, u.failed_attempts = (
            hash_password(pw), True, True, None, 0)
        db.commit()
    print(f"Senha de '{username}' redefinida (troca obrigatória no próximo acesso).")
    print(f"Senha temporária: {pw}")


def cmd_run(args):
    import uvicorn

    from .config import config

    # 1 processo: o hub de WebSocket vive em memória (veja docs/ARQUITETURA.md)
    uvicorn.run("app.main:app", host=config.host, port=args.port or config.port, workers=1,
                proxy_headers=True, log_level="info")


def main():
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate").set_defaults(fn=cmd_migrate)
    sub.add_parser("seed").set_defaults(fn=cmd_seed)
    sub.add_parser("demo").set_defaults(fn=cmd_demo)
    sub.add_parser("clear-data").set_defaults(fn=cmd_clear)
    sub.add_parser("backup").set_defaults(fn=cmd_backup)
    r = sub.add_parser("restore")
    r.add_argument("file")
    r.set_defaults(fn=cmd_restore)
    ra = sub.add_parser("reset-admin")
    ra.add_argument("--username")
    ra.set_defaults(fn=cmd_reset_admin)
    run = sub.add_parser("run")
    run.add_argument("--port", type=int)
    run.set_defaults(fn=cmd_run)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
