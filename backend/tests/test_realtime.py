import pytest
from starlette.websockets import WebSocketDisconnect

from test_tickets import issue, occupy


def token_of(h):
    return h["Authorization"].split()[1]


def drain_until(ws, wanted, limit=20):
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == wanted:
            return msg
    raise AssertionError(f"evento {wanted} não recebido")


def test_ws_requires_valid_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=invalido"):
            pass


def test_ws_events_reach_panel_and_admin(client, env):
    issue(client, env)
    occupy(client, env, "maria")
    with client.websocket_connect(f"/ws?token={token_of(env['painel'])}&panel=PAINEL01") as panel, \
            client.websocket_connect(f"/ws?token={token_of(env['sup'])}") as sup:
        assert panel.receive_json()["type"] == "hello"
        assert sup.receive_json()["type"] == "hello"
        t = client.post("/api/tickets/call-next", headers=env["maria"], json={}).json()["ticket"]
        m = drain_until(panel, "ticket.called")
        assert m["data"]["ticket"]["code"] == "N001" and m["data"]["announce"] is True
        assert m["data"]["ticket"]["counter"]["name"] == "COLETA 01"
        assert drain_until(sup, "queue.updated")["data"]["counts"]["calling"] == 1
        client.post(f"/api/tickets/{t['id']}/recall", headers=env["maria"])
        assert drain_until(panel, "ticket.recalled")["data"]["ticket"]["status"] == "RECHAMADA"
        client.post(f"/api/tickets/{t['id']}/finish", headers=env["maria"])
        assert drain_until(sup, "ticket.attended")
        issue(client, env)
        assert drain_until(sup, "ticket.created")["data"]["ticket"]["code"] == "N002"
    # painel registrou presença
    panels = client.get("/api/admin/panels", headers=env["admin"]).json()
    assert panels[0]["last_seen_at"]


def test_ws_ping_pong(client, env):
    with client.websocket_connect(f"/ws?token={token_of(env['painel'])}") as ws:
        ws.receive_json()
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"
