from conftest import login, make_user


def test_first_access_requires_password_change(client):
    h = login(client, "administrador", "Admin@Teste123")
    assert client.get("/api/auth/me", headers=h).json()["user"]["must_change_password"] is True
    # qualquer outra rota é bloqueada até trocar a senha
    assert client.get("/api/users", headers=h).status_code == 403
    r = client.post("/api/auth/change-password", headers=h,
                    json={"current_password": "Admin@Teste123", "new_password": "12345678"})
    assert r.status_code == 422  # senha fraca
    r = client.post("/api/auth/change-password", headers=h,
                    json={"current_password": "Admin@Teste123", "new_password": "NovaSenha#2026"})
    assert r.status_code == 200
    h2 = login(client, "administrador", "NovaSenha#2026")
    assert client.get("/api/users", headers=h2).status_code == 200


def test_login_invalid_and_lockout(client, admin):
    make_user(client, admin, "fulano", "ATENDENTE")
    for _ in range(5):
        r = client.post("/api/auth/login", json={"username": "fulano", "password": "errada"})
        assert r.status_code == 401
    r = client.post("/api/auth/login", json={"username": "fulano", "password": "Senha#12345"})
    assert r.status_code == 423  # bloqueado mesmo com a senha certa
    uid = next(u["id"] for u in client.get("/api/users", headers=admin).json() if u["username"] == "fulano")
    assert client.patch(f"/api/users/{uid}", headers=admin, json={"unlock": True}).status_code == 200
    login(client, "fulano", "Senha#12345")


def test_passwords_are_hashed(client, admin):
    from app import db as dbmod
    from app.models import User
    make_user(client, admin, "hash1", "ATENDENTE", "Segredo#9999")
    with dbmod.SessionLocal() as db:
        u = db.query(User).filter_by(username="hash1").one()
        assert "Segredo#9999" not in u.password_hash and u.password_hash.startswith("pbkdf2_sha256$")


def test_create_and_block_user(client, admin):
    h = make_user(client, admin, "bloqueavel", "ATENDENTE")
    uid = next(u["id"] for u in client.get("/api/users", headers=admin).json() if u["username"] == "bloqueavel")
    assert client.patch(f"/api/users/{uid}", headers=admin, json={"active": False}).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401  # sessão derrubada
    assert client.post("/api/auth/login", json={"username": "bloqueavel", "password": "Senha#12345"}).status_code == 401
    # duplicado e senha fraca
    r = client.post("/api/users", headers=admin, json={"username": "bloqueavel", "full_name": "X Y",
                                                       "password": "Senha#12345", "role": "ATENDENTE"})
    assert r.status_code == 409
    r = client.post("/api/users", headers=admin, json={"username": "novo1", "full_name": "X Y",
                                                       "password": "abc", "role": "ATENDENTE"})
    assert r.status_code == 422


def test_cannot_lock_last_admin(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()["user"]
    assert client.patch(f"/api/users/{me['id']}", headers=admin, json={"active": False}).status_code == 409
    assert client.patch(f"/api/users/{me['id']}", headers=admin, json={"role": "ATENDENTE"}).status_code == 409


def test_permissions_enforced(client, env):
    assert client.get("/api/users", headers=env["recep"]).status_code == 403
    assert client.post("/api/tickets", headers=env["maria"], json={"ticket_type_id": 1}).status_code == 403
    assert client.get("/api/dashboard", headers=env["maria"]).status_code == 403
    assert client.get("/api/dashboard", headers=env["sup"]).status_code == 200
    assert client.get("/api/panel/state", headers=env["painel"]).status_code == 200
    assert client.get("/api/tickets/waiting", headers=env["painel"]).status_code == 403
    assert client.get("/api/admin/settings", headers=env["sup"]).status_code == 403
    assert client.get("/api/auth/me").status_code == 401


def test_role_permissions_editable_and_audited(client, env):
    admin = env["admin"]
    r = client.put("/api/roles/RECEPCAO/permissions", headers=admin, json={"permissions": ["ticket.view"]})
    assert r.status_code == 200
    assert client.post("/api/tickets", headers=env["recep"], json={"ticket_type_id": 1}).status_code == 403
    assert client.put("/api/roles/ADMINISTRADOR/permissions", headers=admin, json={"permissions": []}).status_code == 409
    actions = [a["action"] for a in client.get("/api/admin/audit", headers=admin).json()]
    assert "perfil.permissoes" in actions and "usuario.criado" in actions


def test_logout_revokes_session(client, env):
    assert client.post("/api/auth/logout", headers=env["maria"]).status_code == 200
    assert client.get("/api/auth/me", headers=env["maria"]).status_code == 401


def test_session_idle_expiry(client, env):
    from datetime import timedelta
    from app import db as dbmod
    from app.models import UserSession
    with dbmod.SessionLocal() as db:
        for s in db.query(UserSession).all():
            s.last_seen_at = s.last_seen_at - timedelta(days=2)
        db.commit()
    assert client.get("/api/auth/me", headers=env["maria"]).status_code == 401
    assert client.get("/api/panel/state", headers=env["painel"]).status_code == 200  # painel não expira
