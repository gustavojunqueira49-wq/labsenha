"""Testa o agente de impressão real (print-agent/agent.py) contra a API, sem rede nem impressora."""
import configparser
import importlib.util
import json
import urllib.error
from pathlib import Path

from test_printing import setup_printer
from test_tickets import issue

spec = importlib.util.spec_from_file_location("agent", Path(__file__).resolve().parents[2] / "print-agent" / "agent.py")
agent_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_mod)


class FakePrinter:
    def __init__(self):
        self.sent, self.state, self.detail = [], "ONLINE", None

    def status(self):
        return self.state, self.detail

    def send(self, data):
        if self.state != "ONLINE":
            raise agent_mod.PrintError(self.state, self.detail or "falha")
        self.sent.append(data)


def make_agent(client, token, printer, tmp_path):
    cfg = configparser.ConfigParser()
    cfg.read_dict({"server": {"url": "http://x", "token": token}, "printer": {"mode": "file", "name": "EPSON"}, "agent": {}})

    class TestAgent(agent_mod.Agent):
        network_up = True

        def api(self, path, payload, timeout=8.0):
            if not self.network_up:
                raise urllib.error.URLError("rede fora")
            r = client.post("/api/agent" + path, json=payload, headers={"X-Agent-Token": self.token})
            if r.status_code >= 400:
                raise urllib.error.HTTPError("x", r.status_code, r.text, {}, None)
            return r.json()

    return TestAgent(cfg, backend=printer, state_file=tmp_path / "state.json")


def statuses(client, env):
    return {j["code"]: j["status"] for j in client.get("/api/print/jobs", headers=env["admin"]).json() if j["code"]}


def test_agent_prints_pending_tickets(client, env, tmp_path):
    token, _, _ = setup_printer(client, env)
    for _ in range(3):
        issue(client, env)
    fp = FakePrinter()
    ag = make_agent(client, token, fp, tmp_path)
    assert ag.step() == 3
    assert len(fp.sent) == 3 and b"N001" in fp.sent[0]
    assert set(statuses(client, env).values()) == {"IMPRESSO"}
    assert client.get("/api/print/status", headers=env["admin"]).json()["agents"][0]["online"] is True


def test_agent_printer_out_of_paper_then_recovers(client, env, tmp_path):
    token, _, _ = setup_printer(client, env)
    issue(client, env); issue(client, env)
    fp = FakePrinter()
    fp.state, fp.detail = "SEM_PAPEL", "Sem papel"
    ag = make_agent(client, token, fp, tmp_path)
    assert ag.step() == 0 and fp.sent == []
    st = client.get("/api/print/status", headers=env["admin"]).json()
    assert st["printers"][0]["status"] == "SEM_PAPEL" and st["queue"]["pending"] == 2  # nada perdido
    fp.state, fp.detail = "ONLINE", None
    assert ag.step() == 2 and len(fp.sent) == 2
    assert client.get("/api/print/status", headers=env["admin"]).json()["printers"][0]["status"] == "ONLINE"


def test_agent_send_failure_reported_and_retried(client, env, tmp_path):
    token, _, _ = setup_printer(client, env)
    issue(client, env)
    fp = FakePrinter()
    ag = make_agent(client, token, fp, tmp_path)
    fp.state, fp.detail = "ONLINE", None
    orig = fp.send
    fp.send = lambda d: (_ for _ in ()).throw(agent_mod.PrintError("OFFLINE", "Impressora desligada"))
    assert ag.step() == 1
    j = client.get("/api/print/jobs", headers=env["admin"]).json()[0]
    assert j["status"] == "PENDENTE" and "desligada" in j["last_error"] and j["attempts"] == 1
    fp.send = orig
    from app import db as dbmod
    from app.models import PrintJob
    with dbmod.SessionLocal() as db:
        db.query(PrintJob).update({"next_attempt_at": None})
        db.commit()
    assert ag.step() == 1 and statuses(client, env) == {"N001": "IMPRESSO"}


def test_agent_no_duplicate_when_result_report_lost(client, env, tmp_path):
    """Imprimiu, mas a rede caiu antes de avisar o servidor: ao voltar, confirma sem reimprimir."""
    token, _, _ = setup_printer(client, env)
    issue(client, env)
    fp = FakePrinter()
    ag = make_agent(client, token, fp, tmp_path)
    real_api = ag.api

    def flaky(path, payload, timeout=8.0):
        if "/result" in path:
            raise urllib.error.URLError("caiu")
        return real_api(path, payload, timeout)

    ag.api = flaky
    assert ag.step() == 1 and len(fp.sent) == 1
    assert statuses(client, env)["N001"] == "ENVIANDO"  # servidor ainda não sabe
    assert json.loads((tmp_path / "state.json").read_text())["unreported"]
    ag.api = real_api
    ag.step()  # reenvia o resultado pendente
    assert statuses(client, env)["N001"] == "IMPRESSO" and len(fp.sent) == 1


def test_agent_survives_server_down_and_invalid_token(client, env, tmp_path):
    token, _, _ = setup_printer(client, env)
    issue(client, env)
    fp = FakePrinter()
    ag = make_agent(client, token, fp, tmp_path)
    ag.network_up = False
    assert ag.step() == 0 and fp.sent == []
    ag.network_up = True
    assert ag.step() == 1
    bad = make_agent(client, "pa_errado", FakePrinter(), tmp_path / "x")
    assert bad.step() == 0
