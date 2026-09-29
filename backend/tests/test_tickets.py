import threading
from datetime import datetime, timedelta, timezone

from app.services.queue import Cand, select_next, simulate_order

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


def types(client, h):
    return {t["code"]: t for t in client.get("/api/ticket-types", headers=h).json()}


def cats(client, h):
    return {c["code"]: c for c in client.get("/api/priorities", headers=h).json()}


def issue(client, env, code="NORMAL", cat=None):
    t = types(client, env["recep"])[code]
    body = {"ticket_type_id": t["id"]}
    if cat:
        body["priority_id"] = cats(client, env["recep"])[cat]["id"]
    r = client.post("/api/tickets", headers=env["recep"], json=body)
    assert r.status_code == 201, r.text
    return r.json()["ticket"]


def occupy(client, env, who, idx=0):
    r = client.post(f"/api/counters/{env['counters'][idx]['id']}/occupy", headers=env[who])
    assert r.status_code == 200, r.text


def test_sequential_codes_and_prefixes(client, env):
    assert [issue(client, env)["code"] for _ in range(3)] == ["N001", "N002", "N003"]
    assert issue(client, env, "PRIORIDADE", "IDOSO")["code"] == "P001"
    assert issue(client, env, "AGENDADO")["code"] == "A001"
    assert issue(client, env)["code"] == "N004"


def test_priority_type_requires_category(client, env):
    t = types(client, env["recep"])["PRIORIDADE"]
    assert client.post("/api/tickets", headers=env["recep"], json={"ticket_type_id": t["id"]}).status_code == 422
    assert client.post("/api/tickets", headers=env["recep"], json={"ticket_type_id": 9999}).status_code == 422
    # tipo inativo (URGENCIA) não pode ser emitido
    urg = next(t for t in client.get("/api/admin/ticket-types", headers=env["admin"]).json() if t["code"] == "URGENCIA")
    assert client.post("/api/tickets", headers=env["recep"], json={"ticket_type_id": urg["id"]}).status_code == 422


def test_concurrent_issue_20_computers_no_duplicates(client, env):
    """20 computadores pedindo senha ao mesmo tempo: nenhuma duplicada, sequência contínua."""
    t = types(client, env["recep"])["NORMAL"]
    barrier = threading.Barrier(20)
    results, errors = [], []

    def worker():
        barrier.wait()
        try:
            r = client.post("/api/tickets", headers=env["recep"], json={"ticket_type_id": t["id"]})
            (results if r.status_code == 201 else errors).append(r.json())
        except Exception as e:  # pragma: no cover
            errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    [th.start() for th in threads]
    [th.join() for th in threads]
    assert not errors, errors
    codes = [r["ticket"]["code"] for r in results]
    assert len(codes) == 20 and len(set(codes)) == 20
    assert sorted(codes) == [f"N{i:03d}" for i in range(1, 21)]


def test_concurrent_calls_never_give_same_ticket(client, env):
    for _ in range(6):
        issue(client, env)
    occupy(client, env, "maria", 0)
    occupy(client, env, "joao", 1)
    barrier = threading.Barrier(2)
    got = []

    def worker(who):
        barrier.wait()
        r = client.post("/api/tickets/call-next", headers=env[who], json={})
        assert r.status_code == 200, r.text
        got.append(r.json()["ticket"]["code"])

    ths = [threading.Thread(target=worker, args=(w,)) for w in ("maria", "joao")]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert len(set(got)) == 2


def test_priority_goes_first_then_arrival(client, env):
    issue(client, env)  # N001
    issue(client, env)  # N002
    issue(client, env, "PRIORIDADE", "GESTANTE")  # P001
    issue(client, env, "PRIORIDADE", "IDOSO_80")  # P002 (categoria de maior rank)
    order = [t["code"] for t in client.get("/api/tickets/waiting", headers=env["recep"]).json()["tickets"]]
    assert order[:2] == ["P002", "P001"] or order[:2] == ["P001", "P002"]
    assert order[0] == "P002"  # IDOSO_80 (rank 1) antes de GESTANTE (rank 5)
    occupy(client, env, "maria")
    assert client.post("/api/tickets/call-next", headers=env["maria"], json={}).json()["ticket"]["code"] == "P002"


def test_full_flow_call_recall_attend_finish(client, env):
    issue(client, env)
    occupy(client, env, "maria")
    t = client.post("/api/tickets/call-next", headers=env["maria"], json={}).json()["ticket"]
    assert t["status"] == "CHAMADA" and t["counter"]["name"] == "COLETA 01" and t["attendant"] == "Maria"
    # não pode chamar outra enquanto há uma ativa
    assert client.post("/api/tickets/call-next", headers=env["maria"], json={}).status_code == 409
    assert client.post(f"/api/tickets/{t['id']}/recall", headers=env["maria"]).json()["ticket"]["status"] == "RECHAMADA"
    # outro atendente não mexe na senha de Maria
    assert client.post(f"/api/tickets/{t['id']}/finish", headers=env["joao"]).status_code == 403
    assert client.post(f"/api/tickets/{t['id']}/attend", headers=env["maria"]).json()["ticket"]["status"] == "EM_ATENDIMENTO"
    assert client.post(f"/api/tickets/{t['id']}/recall", headers=env["maria"]).status_code == 409
    fin = client.post(f"/api/tickets/{t['id']}/finish", headers=env["maria"]).json()["ticket"]
    assert fin["status"] == "ATENDIDA" and fin["finished_at"]
    # histórico completo
    ev = client.get(f"/api/tickets/{t['id']}", headers=env["sup"]).json()["events"]
    assert [e["type"] for e in ev] == ["CRIADA", "CHAMADA", "RECHAMADA", "INICIO_ATENDIMENTO", "ENCERRADA"]
    assert ev[1]["user"] == "Maria" and ev[1]["counter"] == "COLETA 01"
    assert client.post("/api/tickets/call-next", headers=env["maria"], json={}).json()["ticket"] is None


def test_no_show_and_manual_call_back(client, env):
    tk = issue(client, env)
    occupy(client, env, "maria")
    client.post("/api/tickets/call-next", headers=env["maria"], json={})
    r = client.post(f"/api/tickets/{tk['id']}/no-show", headers=env["maria"])
    assert r.json()["ticket"]["status"] == "NAO_COMPARECEU"
    # paciente aparece depois: chamada manual da senha
    r = client.post(f"/api/tickets/{tk['id']}/call", headers=env["maria"], json={})
    assert r.json()["ticket"]["status"] == "CHAMADA"


def test_call_requires_counter(client, env):
    issue(client, env)
    r = client.post("/api/tickets/call-next", headers=env["maria"], json={})
    assert r.status_code == 422 and "guichê" in r.json()["detail"]


def test_counter_occupancy_conflict(client, env):
    occupy(client, env, "maria", 0)
    r = client.post(f"/api/counters/{env['counters'][0]['id']}/occupy", headers=env["joao"])
    assert r.status_code == 409
    assert client.post(f"/api/counters/{env['counters'][0]['id']}/occupy", headers=env["sup"]).status_code == 403  # sem ticket.call


def test_cancel_by_reception(client, env):
    tk = issue(client, env)
    r = client.post(f"/api/tickets/{tk['id']}/cancel", headers=env["recep"], json={"reason": "Paciente desistiu"})
    assert r.json()["ticket"]["status"] == "CANCELADA"
    assert client.post(f"/api/tickets/{tk['id']}/cancel", headers=env["recep"], json={}).status_code == 409
    assert client.get("/api/tickets/waiting", headers=env["recep"]).json()["tickets"] == []


def test_panel_shows_only_code_and_counter(client, env):
    for _ in range(3):
        issue(client, env)
    occupy(client, env, "maria")
    for _ in range(2):
        t = client.post("/api/tickets/call-next", headers=env["maria"], json={}).json()["ticket"]
        client.post(f"/api/tickets/{t['id']}/finish", headers=env["maria"])
    st = client.get("/api/panel/state", headers=env["painel"]).json()
    assert st["current"]["code"] == "N002" and st["current"]["counter"]["name"] == "COLETA 01"
    assert [h["code"] for h in st["history"]] == ["N001"]
    blob = str(st).lower()
    for forbidden in ("cpf", "nascimento", "exame", "diagnostic", "paciente_nome", "patient"):
        assert forbidden not in blob


# ---- política da fila (função pura) ---------------------------------------
def c(i, minutes_ago, level=0, rank=999, pos=1):
    return Cand(id=i, created_at=NOW - timedelta(minutes=minutes_ago), level=level, rank=rank, type_position=pos)


def test_policy_strict_priority():
    cands = [c(1, 30), c(2, 20), c(3, 10, level=1, rank=5)]
    assert select_next(cands, 0, NOW, 0, 0).id == 3
    assert simulate_order(cands, 0, NOW, 0, 0) == [3, 1, 2]


def test_policy_max_consecutive_priority():
    cands = [c(1, 30), c(10, 20, 1, 1), c(11, 19, 1, 1), c(12, 18, 1, 1), c(13, 17, 1, 1)]
    order = simulate_order(cands, 0, NOW, 2, 0)
    assert order == [10, 11, 1, 12, 13]  # após 2 prioritárias entra 1 comum


def test_policy_aging_lets_old_normal_jump():
    cands = [c(1, 50), c(2, 5, level=1, rank=1)]
    assert select_next(cands, 0, NOW, 0, 45).id == 1  # comum esperou 50 min > 45
    assert select_next(cands, 0, NOW, 0, 60).id == 2
    assert select_next(cands, 0, NOW, 0, 0).id == 2  # aging desligado


def test_policy_streak_carries_over(client, env):
    """A contagem de prioritárias consecutivas considera as chamadas já feitas hoje."""
    client.put("/api/admin/settings", headers=env["admin"], json={"queue.max_consecutive_priority": 1, "queue.aging_minutes": 0})
    issue(client, env)
    issue(client, env, "PRIORIDADE", "PCD")
    issue(client, env, "PRIORIDADE", "PCD")
    occupy(client, env, "maria")
    got = []
    for _ in range(3):
        t = client.post("/api/tickets/call-next", headers=env["maria"], json={}).json()["ticket"]
        got.append(t["code"])
        client.post(f"/api/tickets/{t['id']}/finish", headers=env["maria"])
    assert got == ["P001", "N001", "P002"]


def test_counter_accepts_only_configured_types(client, env):
    t = types(client, env["recep"])
    c0 = env["counters"][0]
    r = client.put(f"/api/admin/counters/{c0['id']}", headers=env["admin"], json={
        "code": c0["code"], "name": c0["name"], "accepted_type_ids": [t["AGENDADO"]["id"]], "active": True})
    assert r.status_code == 200
    issue(client, env)
    occupy(client, env, "maria", 0)
    assert client.post("/api/tickets/call-next", headers=env["maria"], json={}).json()["ticket"] is None
    issue(client, env, "AGENDADO")
    assert client.post("/api/tickets/call-next", headers=env["maria"], json={}).json()["ticket"]["code"] == "A001"


def test_expire_stale_keeps_history(client, env):
    from app import db as dbmod
    from app.models import Ticket
    from app.services import queue
    tk = issue(client, env)
    with dbmod.SessionLocal() as db:
        t = db.get(Ticket, tk["id"])
        t.service_date = t.service_date - timedelta(days=1)
        db.commit()
        assert queue.expire_stale(db) == 1
        db.commit()
        t = db.get(Ticket, tk["id"])
        assert t.status == "CANCELADA" and "virada" in t.status_reason
    assert client.get(f"/api/tickets/{tk['id']}", headers=env["sup"]).status_code == 200  # histórico preservado


def test_unique_constraint_is_last_line_of_defense(client, env):
    import pytest
    from sqlalchemy.exc import IntegrityError
    from app import db as dbmod
    from app.models import Ticket
    tk = issue(client, env)
    with dbmod.SessionLocal() as db:
        t = db.get(Ticket, tk["id"])
        db.add(Ticket(code="X", number=t.number, ticket_type_id=t.ticket_type_id, service_date=t.service_date,
                      seq_date=t.seq_date))
        with pytest.raises(IntegrityError):
            db.commit()
