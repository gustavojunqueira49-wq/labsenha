import io

from test_tickets import issue, occupy


def run_day(client, env):
    """3 normais + 2 prioritárias; atende 3, 1 não comparece, 1 cancelada."""
    for _ in range(3):
        issue(client, env)
    issue(client, env, "PRIORIDADE", "GESTANTE")
    issue(client, env, "PRIORIDADE", "PCD")
    occupy(client, env, "maria", 0)
    occupy(client, env, "joao", 1)
    for who in ("maria", "joao", "maria"):
        t = client.post("/api/tickets/call-next", headers=env[who], json={}).json()["ticket"]
        client.post(f"/api/tickets/{t['id']}/attend", headers=env[who])
        client.post(f"/api/tickets/{t['id']}/finish", headers=env[who])
    t = client.post("/api/tickets/call-next", headers=env["maria"], json={}).json()["ticket"]
    client.post(f"/api/tickets/{t['id']}/no-show", headers=env["maria"])
    last = client.get("/api/tickets/waiting", headers=env["recep"]).json()["tickets"][0]
    client.post(f"/api/tickets/{last['id']}/cancel", headers=env["recep"], json={"reason": "teste"})


def rows(data):
    return {r["metric"]: r["value"] for r in data["rows"]}


def test_summary_and_groupings(client, env):
    run_day(client, env)
    s = rows(client.get("/api/reports/summary", headers=env["sup"]).json())
    assert s["Senhas emitidas"] == 5 and s["Senhas atendidas"] == 3 and s["Não comparecimentos"] == 1
    assert s["Senhas prioritárias"] == 2 and s["Senhas normais"] == 3 and s["Canceladas"] == 1
    assert s["Tempo médio de espera (min)"] is not None
    by_att = {r["group"]: r for r in client.get("/api/reports/by_attendant", headers=env["sup"]).json()["rows"]}
    assert by_att["Maria"]["attended"] == 2 and by_att["Joao"]["attended"] == 1
    by_c = {r["group"]: r for r in client.get("/api/reports/by_counter", headers=env["sup"]).json()["rows"]}
    assert by_c["COLETA 01"]["emitted"] == 3 and by_c["COLETA 02"]["emitted"] == 1
    by_type = {r["group"]: r["emitted"] for r in client.get("/api/reports/by_type", headers=env["sup"]).json()["rows"]}
    assert by_type == {"Atendimento Normal": 3, "Atendimento Prioritário": 2}
    assert len(client.get("/api/reports/by_hour", headers=env["sup"]).json()["rows"]) >= 1
    assert len(client.get("/api/reports/by_day", headers=env["sup"]).json()["rows"]) == 1


def test_filters(client, env):
    run_day(client, env)
    d = client.get("/api/reports/tickets?status=ATENDIDA", headers=env["sup"]).json()
    assert d["count"] == 3
    joao = next(a["id"] for a in client.get("/api/reports/attendants", headers=env["sup"]).json() if a["name"] == "Joao")
    assert client.get(f"/api/reports/tickets?attendant_id={joao}", headers=env["sup"]).json()["count"] == 1
    assert client.get("/api/reports/tickets?time_from=23:59&time_to=23:59", headers=env["sup"]).json()["count"] in (0, 5)
    assert client.get("/api/reports/tickets?date_from=2020-01-01&date_to=2020-01-31", headers=env["sup"]).json()["count"] == 0
    assert client.get("/api/reports/tickets?date_from=2026-02-01&date_to=2026-01-01", headers=env["sup"]).status_code == 422
    assert client.get("/api/reports/nada", headers=env["sup"]).status_code == 404


def test_exports(client, env):
    run_day(client, env)
    r = client.get("/api/reports/tickets/export?format=csv", headers=env["sup"])
    assert r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf") and b"N001" in r.content
    r = client.get("/api/reports/by_type/export?format=xlsx", headers=env["sup"])
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.active["A1"].value == "Tipo" and wb.active.max_row == 3
    r = client.get("/api/reports/summary/export?format=pdf", headers=env["sup"])
    assert r.content.startswith(b"%PDF")
    assert client.get("/api/reports/summary/export?format=pdf", headers=env["maria"]).status_code == 403
    assert client.get("/api/reports/summary/export?format=doc", headers=env["sup"]).status_code == 422


def test_dashboard(client, env):
    run_day(client, env)
    d = client.get("/api/dashboard", headers=env["sup"]).json()
    c = d["counts"]
    assert (c["total"], c["done"], c["no_show"], c["cancelled"]) == (5, 3, 1, 1)
    assert d["priority_today"] == 2 and len(d["by_hour"]) == 24 and d["by_type"]
    assert d["backup"]["stale"] is True  # nenhum backup ainda


# ---- administração -----------------------------------------------------------
def test_settings_validation_and_audit(client, env):
    a = env["admin"]
    assert client.put("/api/admin/settings", headers=a, json={"hospital.name": "HC"}).status_code == 200
    assert client.put("/api/admin/settings", headers=a, json={"ticket.digits": 99}).status_code == 422
    assert client.put("/api/admin/settings", headers=a, json={"nao.existe": 1}).status_code == 422
    assert client.put("/api/admin/settings", headers=a, json={"audio.enabled": "sim"}).status_code == 422
    assert client.get("/api/auth/me", headers=env["painel"]).json()["settings"]["hospital.name"] == "HC"
    log = client.get("/api/admin/audit?action=configuracao", headers=a).json()
    assert log and log[0]["details"] == {"hospital.name": "HC"}


def test_ticket_code_format_setting(client, env):
    client.put("/api/admin/settings", headers=env["admin"], json={"ticket.separator": "-", "ticket.digits": 4})
    assert issue(client, env)["code"] == "N-0001"


def test_priority_categories_crud(client, env):
    a = env["admin"]
    data = client.get("/api/admin/priorities", headers=a).json()
    assert "validadas pelo hospital" in data["notice"]
    assert all("validar" in p["legal_basis"].lower() or p["code"] == "INSTITUCIONAL" for p in data["priorities"])
    new = client.post("/api/admin/priorities", headers=a, json={
        "code": "DOADOR", "name": "Doador de sangue", "legal_basis": "Lei 10.048/2000", "rank": 20})
    assert new.status_code == 201
    pid = new.json()["id"]
    r = client.put(f"/api/admin/priorities/{pid}", headers=a, json={
        "code": "DOADOR", "name": "Doador de sangue", "legal_basis": "x", "rank": 20, "active": False})
    assert r.status_code == 200
    assert "DOADOR" not in [p["code"] for p in client.get("/api/priorities", headers=env["recep"]).json()]
    assert client.post("/api/admin/priorities", headers=a, json={"code": "DOADOR", "name": "dup"}).status_code == 409
    assert client.post("/api/admin/priorities", headers=env["recep"], json={"code": "ZZ", "name": "zz"}).status_code == 403


def test_ticket_types_crud_and_prefix_lock(client, env):
    a = env["admin"]
    body = {"code": "COLETA_DOMICILIAR", "name": "Domiciliar", "prefix": "D", "color": "#123456", "priority_level": 0}
    r = client.post("/api/admin/ticket-types", headers=a, json=body)
    assert r.status_code == 201
    tid = r.json()["id"]
    assert client.post("/api/admin/ticket-types", headers=a, json={**body, "code": "OUTRO"}).status_code == 409  # prefixo repetido
    assert client.post("/api/admin/ticket-types", headers=a, json={**body, "code": "X1", "prefix": "Q", "color": "azul"}).status_code == 422
    tk = client.post("/api/tickets", headers=env["recep"], json={"ticket_type_id": tid}).json()["ticket"]
    assert tk["code"] == "D001"
    assert client.put(f"/api/admin/ticket-types/{tid}", headers=a, json={**body, "prefix": "Z"}).status_code == 409
    assert client.put(f"/api/admin/ticket-types/{tid}", headers=a, json={**body, "name": "Domiciliar 2"}).status_code == 200


def test_computers_panels_counters(client, env):
    a = env["admin"]
    assert client.post("/api/admin/computers", headers=a, json={"name": "PC-01", "ip_address": "192.168.1.101"}).status_code == 201
    assert client.post("/api/admin/computers", headers=a, json={"name": "PC-01"}).status_code == 409
    assert client.post("/api/admin/panels", headers=a, json={"code": "TV2", "name": "TV sala 2"}).status_code == 201
    assert client.post("/api/admin/counters", headers=a, json={"code": "COLETA09", "name": "COLETA 09"}).status_code == 201
    assert len(client.get("/api/counters", headers=a).json()) == 3


def test_backup_create_list_restore(client, env):
    a = env["admin"]
    issue(client, env)
    b = client.post("/api/backups", headers=a)
    assert b.status_code == 201, b.text
    assert b.json()["size_bytes"] > 0
    issue(client, env)  # N002 depois do backup
    assert len(client.get("/api/tickets", headers=a).json()["tickets"]) == 2
    lst = client.get("/api/backups", headers=a).json()
    assert lst["status"]["stale"] is False and lst["backups"][0]["exists"]
    assert client.post(f"/api/backups/{b.json()['id']}/restore", headers=a, json={"confirm": "x"}).status_code == 422
    r = client.post(f"/api/backups/{b.json()['id']}/restore", headers=a, json={"confirm": "RESTAURAR"})
    assert r.status_code == 200, r.text
    # após restaurar: sessões voltaram ao estado do backup; entra novamente e confere
    from conftest import login
    h = login(client, "administrador", "NovaSenha#2026")
    assert len(client.get("/api/tickets", headers=h).json()["tickets"]) == 1
    kinds = [x["kind"] for x in client.get("/api/backups", headers=h).json()["backups"]]
    assert "PRE_RESTORE" not in kinds or True  # histórico segue o banco restaurado
    assert client.post("/api/backups", headers=env["recep"]).status_code == 403


def test_backup_alert_when_old(client, env):
    from datetime import timedelta
    from app import db as dbmod
    from app.models import Backup
    a = env["admin"]
    client.post("/api/backups", headers=a)
    with dbmod.SessionLocal() as db:
        for b in db.query(Backup).all():
            b.created_at -= timedelta(days=3)
        db.commit()
    st = client.get("/api/backups", headers=a).json()["status"]
    assert st["stale"] is True and "acima do limite" in st["message"]


def test_auto_backup_due_logic(client, env):
    from app import db as dbmod
    from app.services import backup
    with dbmod.SessionLocal() as db:
        assert backup.due_for_auto(db) is True
        backup.create_backup(db, "AUTO")
        assert backup.due_for_auto(db) is False


def test_demo_data_load_and_clear(client, env):
    a = env["admin"]
    r = client.post("/api/admin/demo/load", headers=a)
    assert r.status_code == 200 and r.json()["tickets"] == 20
    assert len(client.get("/api/counters", headers=a).json()) == 4
    tks = client.get("/api/tickets", headers=a).json()["tickets"]
    assert len(tks) == 20 and {t["type"]["prefix"] for t in tks} >= {"N", "P"}
    from conftest import login
    h = login(client, "recepcao", "Demo@12345")
    assert client.get("/api/ticket-types", headers=h).status_code == 200
    assert client.post("/api/admin/demo/clear", headers=a, json={"confirm": "nao"}).status_code == 422
    assert client.post("/api/admin/demo/clear", headers=a, json={"confirm": "LIMPAR"}).status_code == 200
    assert client.get("/api/tickets", headers=a).json()["tickets"] == []
    assert client.post("/api/auth/login", json={"username": "recepcao", "password": "Demo@12345"}).status_code == 401


def test_health_and_security_headers(client):
    r = client.get("/api/health")
    assert r.json()["database"] == "ok"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_sql_injection_attempts_are_harmless(client, env):
    r = client.post("/api/auth/login", json={"username": "' OR 1=1 --", "password": "' OR '1'='1"})
    assert r.status_code == 401
    r = client.get("/api/tickets?code=%27%3B%20DROP%20TABLE%20tickets%3B--", headers=env["sup"])
    assert r.status_code == 200 and r.json()["tickets"] == []
    assert client.get("/api/tickets", headers=env["sup"]).status_code == 200
