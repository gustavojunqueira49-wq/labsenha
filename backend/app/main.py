from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from . import __version__, db as dbmod, maintenance
from .config import config
from .deps import authenticate
from .events import hub
from .models import Panel
from .routers import admin, auth, backups, printing as print_router, reports, tickets, users
from .services import queue, seed

log = logging.getLogger("app")

API_DESCRIPTION = """
API do **Sistema de Fila e Senhas — Coleta de Exames Laboratoriais**.

* Autenticação: `POST /api/auth/login` → use o `token` no cabeçalho `Authorization: Bearer <token>`.
* Tempo real: WebSocket em `/ws?token=<token>` (eventos `ticket.created`, `ticket.called`, ...).
* Agente de impressão: rotas `/api/agent/*` com cabeçalho `X-Agent-Token`.
"""


def init_database() -> None:
    """Cria estrutura (somente SQLite/dev) e dados básicos. Em PostgreSQL use `python -m app.cli migrate`."""
    if config.is_sqlite and "roles" not in inspect(dbmod.engine).get_table_names():
        from alembic import command
        from alembic.config import Config as AlembicConfig

        base = Path(__file__).resolve().parents[1]
        cfg = AlembicConfig(str(base / "alembic.ini"))
        cfg.set_main_option("script_location", str(base / "migrations"))
        command.upgrade(cfg, "head")
    if "roles" not in inspect(dbmod.engine).get_table_names():
        log.error("Banco sem estrutura. Execute: python -m app.cli migrate")
        return
    with dbmod.SessionLocal() as db:
        temp = seed.seed_base(db)
    if temp:
        path = seed.write_first_access_file(config.initial_admin_username, temp)
        msg = f"PRIMEIRO ACESSO — usuário '{config.initial_admin_username}', senha temporária em {path}"
        log.warning(msg)
        print("=" * 70 + f"\n{msg}\n" + "=" * 70, flush=True)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    hub.attach_loop(asyncio.get_running_loop())
    try:
        await asyncio.to_thread(init_database)
    except Exception:
        log.exception("Não foi possível inicializar o banco (o servidor continuará tentando)")
    task = None
    if not config.disable_background_tasks:
        task = asyncio.create_task(maintenance.loop(config.maintenance_interval_seconds))
    yield
    if task:
        task.cancel()


app = FastAPI(title="Fila de Senhas — Laboratório", version=__version__, description=API_DESCRIPTION,
              lifespan=lifespan, docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json")

if config.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in config.cors_origins.split(",")],
                       allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/docs") or request.url.path.startswith("/api/redoc"):
        pass  # Swagger/ReDoc precisam de scripts próprios
    else:
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' ws: wss:; media-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
    resp.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
    return resp


@app.exception_handler(queue.QueueError)
async def queue_error(_: Request, exc: queue.QueueError):
    return JSONResponse({"detail": exc.message, **exc.extra}, status_code=exc.status_code)


@app.exception_handler(OperationalError)
async def db_down(_: Request, exc: OperationalError):
    log.error("Banco indisponível: %s", exc)
    return JSONResponse({"detail": "Banco de dados indisponível. Aguarde e tente novamente."}, status_code=503)


@app.exception_handler(DBAPIError)
async def db_error(_: Request, exc: DBAPIError):
    log.exception("Erro de banco")
    return JSONResponse({"detail": "Erro ao acessar o banco de dados."}, status_code=500)


api = "/api"
for r in (auth.router, auth.occupy_router, users.router, tickets.router, admin.router, print_router.router,
          print_router.agent_router, reports.router, backups.router):
    app.include_router(r, prefix=api)


@app.get("/api/health", tags=["Sistema"])
def health():
    try:
        with dbmod.engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok", "version": __version__}
    except Exception as e:
        return JSONResponse({"status": "degraded", "database": "error", "detail": str(e)[:200]}, status_code=503)


@app.get("/api/system/clients", tags=["Sistema"])
def ws_clients():
    return {"connected": len(hub.clients_info())}


# ---- WebSocket ---------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = "", panel: str = ""):
    def _auth():
        with dbmod.SessionLocal() as db:
            user, _ = authenticate(db, token)
            if user.must_change_password:
                raise PermissionError
            perms = {p.code for p in user.role.permissions}
            if panel:
                p = db.scalars(select(Panel).where(Panel.code == panel.upper())).first()
                if p:
                    from .db import utcnow
                    p.last_seen_at = utcnow()
                    db.commit()
            return user.username, perms

    try:
        username, perms = await asyncio.to_thread(_auth)
    except Exception:
        await ws.close(code=4401)
        return
    await ws.accept()
    cid, q = hub.register({"user": username, "panel": panel or None})
    await ws.send_json({"type": "hello", "data": {"user": username, "version": __version__}})
    try:
        async def sender():
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=25)
                    await ws.send_text(payload)
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "ping"})

        async def receiver():
            while True:
                msg = await ws.receive_text()
                if msg == "ping":
                    await ws.send_json({"type": "pong"})

        t1, t2 = asyncio.create_task(sender()), asyncio.create_task(receiver())
        done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        pass
    except Exception:
        log.debug("ws encerrado", exc_info=True)
    finally:
        hub.unregister(cid)


# ---- Frontend estático (mesma origem: sem CORS, sem internet) ---------------------------
if Path(config.frontend_dir).is_dir():
    app.mount("/", StaticFiles(directory=str(config.frontend_dir), html=True), name="frontend")
