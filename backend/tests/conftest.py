"""Testes rodam em SQLite (padrão) ou PostgreSQL: TEST_DATABASE_URL=postgresql+psycopg://..."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="senhas_test_")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["DISABLE_BACKGROUND_TASKS"] = "1"
os.environ["DATA_DIR"] = _tmp
os.environ["BACKUP_DIR"] = f"{_tmp}/backups"
os.environ["INITIAL_ADMIN_PASSWORD"] = "Admin@Teste123"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db as dbmod  # noqa: E402
from app import models  # noqa: E402,F401
from app.db import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.services import seed  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(dbmod.engine)
    Base.metadata.create_all(dbmod.engine)
    with dbmod.SessionLocal() as db:
        seed.seed_base(db)
    with TestClient(app) as c:
        yield c


def login(client, username, password) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def admin(client):
    """Administrador já com a senha trocada."""
    h = login(client, "administrador", "Admin@Teste123")
    r = client.post("/api/auth/change-password", headers=h,
                    json={"current_password": "Admin@Teste123", "new_password": "NovaSenha#2026"})
    assert r.status_code == 200, r.text
    return login(client, "administrador", "NovaSenha#2026")


def make_user(client, admin, username, role, password="Senha#12345"):
    r = client.post("/api/users", headers=admin, json={
        "username": username, "full_name": username.title(), "password": password, "role": role,
        "must_change_password": False})
    assert r.status_code == 201, r.text
    return login(client, username, password)


@pytest.fixture()
def env(client, admin):
    e = {"admin": admin}
    for name, role in (("recep", "RECEPCAO"), ("maria", "ATENDENTE"), ("joao", "ATENDENTE"),
                       ("painel", "PAINEL"), ("sup", "SUPERVISAO")):
        e[name] = make_user(client, admin, name, role)
    e["counters"] = client.get("/api/counters", headers=admin).json()
    return e
