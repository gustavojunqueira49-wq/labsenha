import base64
import socket
import threading

from app import db as dbmod
from app.services import printing
from test_tickets import issue


def setup_printer(client, env, **kw):
    a = client.post("/api/print/agents", headers=env["admin"], json={"name": "Agente Recepção"}).json()
    body = {"name": "EPSON TM-T20", "agent_id": a["id"], "is_default": True, **kw}
    p = client.post("/api/print/printers", headers=env["admin"], json=body)
    assert p.status_code == 201, p.text
    return a["token"], a["id"], p.json()["id"]


def ah(token):
    return {"X-Agent-Token": token}


def test_ticket_generates_print_job_and_agent_prints(client, env):
    token, _, pid = setup_printer(client, env)
    tk = issue(client, env, "PRIORIDADE", "IDOSO")
    r = client.post("/api/agent/jobs/claim", headers=ah(token), json={"printer_status": "ONLINE"})
    jobs = r.json()["jobs"]
    assert len(jobs) == 1 and jobs[0]["code"] == tk["code"]
    raw = base64.b64decode(jobs[0]["escpos_b64"])
    assert tk["code"].encode() in raw and raw.startswith(b"\x1b@") and raw.endswith(b"\x1dV\x42\x00")
    assert "P001" in jobs[0]["text"] and "HOSPITAL" in jobs[0]["text"]
    # mesmo job não é entregue duas vezes
    assert client.post("/api/agent/jobs/claim", headers=ah(token), json={}).json()["jobs"] == []
    r = client.post(f"/api/agent/jobs/{jobs[0]['id']}/result", headers=ah(token), json={"ok": True})
    assert r.json()["status"] == "IMPRESSO"
    st = client.get("/api/print/status", headers=env["admin"]).json()
    assert st["queue"]["pending"] == 0 and st["printers"][0]["status"] == "ONLINE"
    assert st["agents"][0]["online"] is True


def test_printer_failure_does_not_lose_ticket_and_recovers(client, env):
    token, _, pid = setup_printer(client, env)
    tks = [issue(client, env) for _ in range(3)]
    # impressora sem papel: agente avisa e não recebe jobs; nada é perdido
    r = client.post("/api/agent/jobs/claim", headers=ah(token), json={"printer_status": "SEM_PAPEL", "printer_detail": "Sem papel"})
    assert r.json()["jobs"] == []
    st = client.get("/api/print/status", headers=env["admin"]).json()
    assert st["printers"][0]["status"] == "SEM_PAPEL" and st["queue"]["pending"] == 3
    # tentativa que falha no meio: job volta para a fila com erro registrado
    jobs = client.post("/api/agent/jobs/claim", headers=ah(token), json={"printer_status": "ONLINE"}).json()["jobs"]
    assert len(jobs) == 3
    client.post(f"/api/agent/jobs/{jobs[0]['id']}/result", headers=ah(token),
                json={"ok": False, "error": "Impressora desligada", "printer_status": "OFFLINE"})
    listed = {j["id"]: j for j in client.get("/api/print/jobs", headers=env["admin"]).json()}
    assert listed[jobs[0]["id"]]["status"] == "PENDENTE" and listed[jobs[0]["id"]]["attempts"] == 1
    assert "desligada" in listed[jobs[0]["id"]]["last_error"]
    # devolve os outros (agente caiu antes de imprimir) e simula tempo passando
    with dbmod.SessionLocal() as db:
        from app.models import PrintJob
        for j in db.query(PrintJob).all():
            j.next_attempt_at = None
            if j.status == "ENVIANDO":
                j.claimed_at = j.claimed_at.replace(year=2000)  # travado há muito tempo
        db.commit()
        assert printing.reset_stale(db) == 2
        db.commit()
    # impressora volta: todas as 3 senhas saem, em ordem
    jobs = client.post("/api/agent/jobs/claim", headers=ah(token), json={"printer_status": "ONLINE"}).json()["jobs"]
    assert [j["code"] for j in jobs] == [t["code"] for t in tks]
    for j in jobs:
        assert client.post(f"/api/agent/jobs/{j['id']}/result", headers=ah(token), json={"ok": True}).json()["status"] == "IMPRESSO"


def test_job_moves_to_error_after_max_attempts_and_can_be_retried(client, env):
    token, _, _ = setup_printer(client, env)
    client.put("/api/admin/settings", headers=env["admin"], json={"print.max_attempts": 2})
    issue(client, env)
    for _ in range(2):
        with dbmod.SessionLocal() as db:
            from app.models import PrintJob
            for j in db.query(PrintJob).all():
                j.next_attempt_at = None
            db.commit()
        j = client.post("/api/agent/jobs/claim", headers=ah(token), json={}).json()["jobs"][0]
        client.post(f"/api/agent/jobs/{j['id']}/result", headers=ah(token), json={"ok": False, "error": "x"})
    st = client.get("/api/print/status", headers=env["admin"]).json()
    assert st["queue"]["error"] == 1
    assert client.post("/api/print/jobs/retry-all", headers=env["admin"]).json()["requeued"] == 1
    j = client.post("/api/agent/jobs/claim", headers=ah(token), json={}).json()["jobs"][0]
    assert client.post(f"/api/agent/jobs/{j['id']}/result", headers=ah(token), json={"ok": True}).json()["status"] == "IMPRESSO"


def test_ticket_issued_without_printer_is_printed_when_one_is_configured(client, env):
    tk = issue(client, env)  # nenhuma impressora ainda: a senha existe e o job espera
    assert client.get("/api/print/status", headers=env["admin"]).json()["unassigned_jobs"] == 1
    token, _, _ = setup_printer(client, env)
    jobs = client.post("/api/agent/jobs/claim", headers=ah(token), json={}).json()["jobs"]
    assert [j["code"] for j in jobs] == [tk["code"]]


def test_agent_offline_detection_and_events(client, env):
    from app import maintenance
    from app.events import hub
    token, aid, _ = setup_printer(client, env)
    client.post("/api/agent/heartbeat", headers=ah(token), json={"printer_status": "ONLINE", "hostname": "PC-REC"})
    assert client.get("/api/print/status", headers=env["admin"]).json()["agents"][0]["online"] is True
    with dbmod.SessionLocal() as db:
        from datetime import timedelta
        from app.models import PrintAgent
        a = db.get(PrintAgent, aid)
        a.last_seen_at = a.last_seen_at - timedelta(minutes=5)
        db.commit()
    hub.history.clear()
    maintenance.tick()
    st = client.get("/api/print/status", headers=env["admin"]).json()
    assert st["agents"][0]["online"] is False and st["printers"][0]["status"] == "OFFLINE"
    assert any(m["type"] == "agent.status" for m in hub.history)


def test_agent_auth_and_isolation(client, env):
    assert client.post("/api/agent/jobs/claim", headers=ah("pa_invalido"), json={}).status_code == 401
    assert client.post("/api/agent/jobs/claim", json={}).status_code == 401
    t1, _, _ = setup_printer(client, env)
    issue(client, env)
    a2 = client.post("/api/print/agents", headers=env["admin"], json={"name": "Outro"}).json()
    assert client.post("/api/agent/jobs/claim", headers=ah(a2["token"]), json={}).json()["jobs"] == []
    job_id = client.get("/api/print/jobs", headers=env["admin"]).json()[0]["id"]
    assert client.post(f"/api/agent/jobs/{job_id}/result", headers=ah(a2["token"]), json={"ok": True}).status_code == 404


def test_test_print_and_reprint(client, env):
    token, _, pid = setup_printer(client, env)
    tk = issue(client, env)
    assert client.post("/api/print/test", headers=env["admin"], json={}).status_code == 200
    assert client.post(f"/api/tickets/{tk['id']}/reprint", headers=env["recep"]).status_code == 200
    jobs = client.post("/api/agent/jobs/claim", headers=ah(token), json={}).json()["jobs"]
    kinds = sorted(j["kind"] for j in jobs)
    assert kinds == ["TEST", "TICKET", "TICKET"]
    assert "TESTE" in next(j for j in jobs if j["kind"] == "TEST")["text"]
    assert client.post("/api/print/test", headers=env["maria"], json={}).status_code == 403


def test_layout_is_configurable(client, env):
    token, _, pid = setup_printer(client, env, chars_per_line=32, margin_top=0, margin_bottom=0, cut=False, code_size=6)
    client.put("/api/admin/settings", headers=env["admin"], json={
        "hospital.name": "HOSPITAL SÃO JOSÉ", "lab.name": "LABORATÓRIO CENTRAL", "ticket.message": "AGUARDE", "ticket.footer": "Obrigado"})
    issue(client, env)
    j = client.post("/api/agent/jobs/claim", headers=ah(token), json={}).json()["jobs"][0]
    raw = base64.b64decode(j["escpos_b64"])
    assert "LABORATÓRIO CENTRAL".encode("cp850") in raw and b"\x1dV" not in raw and b"\x1d!\x55" in raw  # tamanho 6
    assert "Obrigado" in j["text"] and "LABORATÓRIO CENTRAL" in j["text"]
    prev = client.get(f"/api/print/printers/{pid}/preview", headers=env["admin"]).json()["text"]
    assert "P001" in prev


def test_network_printer_scenario_b(client, env):
    """Impressora de rede: o servidor envia direto por TCP 9100 (sem agente)."""
    received = []
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    port = srv.getsockname()[1]

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            data = b""
            while chunk := conn.recv(4096):
                data += chunk
            received.append(data)
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    p = client.post("/api/print/printers", headers=env["admin"], json={
        "name": "Epson Rede", "connection": "NETWORK", "host": "127.0.0.1", "port": port})
    assert p.status_code == 201
    issue(client, env)
    with dbmod.SessionLocal() as db:
        printing.process_network_jobs(db)
        db.commit()
    srv.close()
    assert received and b"N001" in received[0]
    st = client.get("/api/print/status", headers=env["admin"]).json()
    assert st["queue"]["pending"] == 0 and st["printers"][0]["status"] == "ONLINE"


def test_network_printer_down_keeps_job(client, env):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # porta fechada
    client.post("/api/print/printers", headers=env["admin"], json={
        "name": "Epson Rede", "connection": "NETWORK", "host": "127.0.0.1", "port": port})
    issue(client, env)
    with dbmod.SessionLocal() as db:
        printing.process_network_jobs(db)
        db.commit()
    st = client.get("/api/print/status", headers=env["admin"]).json()
    assert st["queue"]["pending"] == 1 and st["printers"][0]["status"] == "OFFLINE"
