"""Relatórios e dashboard. Agregação em Python (portável entre PostgreSQL e SQLite)."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import config
from ..models import Ticket
from .queue import counts_today, local_today

KINDS = {
    "tickets": "Senhas (detalhado)", "summary": "Resumo do período", "by_hour": "Movimento por hora",
    "by_day": "Movimento por dia", "by_type": "Movimento por tipo de senha",
    "by_attendant": "Atendimento por funcionário", "by_counter": "Atendimento por guichê",
    "by_status": "Senhas por situação",
}
STATUS_LABEL = {"AGUARDANDO": "Aguardando", "CHAMADA": "Chamada", "RECHAMADA": "Rechamada",
                "EM_ATENDIMENTO": "Em atendimento", "ATENDIDA": "Atendida",
                "NAO_COMPARECEU": "Não compareceu", "CANCELADA": "Cancelada"}


def _local(dt_: datetime | None) -> datetime | None:
    return dt_.astimezone(config.tz) if dt_ else None


def _fmt(dt_: datetime | None) -> str:
    d = _local(dt_)
    return d.strftime("%d/%m/%Y %H:%M:%S") if d else ""


def _mins(a: datetime | None, b: datetime | None) -> float | None:
    return round((b - a).total_seconds() / 60, 1) if a and b else None


def _avg(vals: list[float | None]) -> float | None:
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), 1) if v else None


def fetch(db: Session, f: dict) -> list[Ticket]:
    d_from: date = f.get("date_from") or local_today()
    d_to: date = f.get("date_to") or d_from
    q = select(Ticket).where(Ticket.service_date >= d_from, Ticket.service_date <= d_to)
    if f.get("type_id"):
        q = q.where(Ticket.ticket_type_id == f["type_id"])
    if f.get("attendant_id"):
        q = q.where(Ticket.attendant_id == f["attendant_id"])
    if f.get("counter_id"):
        q = q.where(Ticket.counter_id == f["counter_id"])
    if f.get("status"):
        q = q.where(Ticket.status == f["status"])
    rows = list(db.scalars(q.order_by(Ticket.created_at, Ticket.id)).unique())
    t_from: time | None = f.get("time_from")
    t_to: time | None = f.get("time_to")
    if t_from or t_to:
        def ok(t: Ticket) -> bool:
            lt = _local(t.created_at).time()
            return (not t_from or lt >= t_from) and (not t_to or lt <= t_to)
        rows = [t for t in rows if ok(t)]
    return rows


def _stats(ts: list[Ticket]) -> dict:
    return {
        "emitted": len(ts),
        "attended": sum(t.status == "ATENDIDA" for t in ts),
        "priority": sum(t.ticket_type.priority_level > 0 for t in ts),
        "normal": sum(t.ticket_type.priority_level <= 0 for t in ts),
        "no_show": sum(t.status == "NAO_COMPARECEU" for t in ts),
        "cancelled": sum(t.status == "CANCELADA" for t in ts),
        "avg_wait_min": _avg([_mins(t.created_at, t.called_at) for t in ts]),
        "avg_service_min": _avg([_mins(t.started_at, t.finished_at) for t in ts if t.status == "ATENDIDA"]),
    }


def _group_table(ts: list[Ticket], keyfn, label: str) -> dict:
    groups: dict = defaultdict(list)
    for t in ts:
        groups[keyfn(t)].append(t)
    rows = []
    for k in sorted(groups, key=lambda x: str(x)):
        s = _stats(groups[k])
        rows.append({"group": k, "emitted": s["emitted"], "attended": s["attended"], "priority": s["priority"],
                     "normal": s["normal"], "no_show": s["no_show"], "cancelled": s["cancelled"],
                     "avg_wait_min": s["avg_wait_min"], "avg_service_min": s["avg_service_min"]})
    cols = [("group", label), ("emitted", "Emitidas"), ("attended", "Atendidas"), ("priority", "Prioritárias"),
            ("normal", "Normais"), ("no_show", "Não compareceram"), ("cancelled", "Canceladas"),
            ("avg_wait_min", "Espera média (min)"), ("avg_service_min", "Atendimento médio (min)")]
    return {"columns": [{"key": k, "label": lb} for k, lb in cols], "rows": rows}


def build(db: Session, kind: str, f: dict) -> dict:
    if kind not in KINDS:
        raise KeyError(kind)
    ts = fetch(db, f)
    if kind == "tickets":
        cols = [("code", "Senha"), ("type", "Tipo"), ("category", "Categoria"), ("status", "Situação"),
                ("created_at", "Retirada"), ("called_at", "Chamada"), ("started_at", "Início"),
                ("finished_at", "Fim"), ("counter", "Guichê"), ("attendant", "Atendente"),
                ("wait_min", "Espera (min)"), ("service_min", "Atendimento (min)")]
        rows = [{"code": t.code, "type": t.ticket_type.name, "category": t.priority.name if t.priority else "",
                 "status": STATUS_LABEL[t.status], "created_at": _fmt(t.created_at), "called_at": _fmt(t.called_at),
                 "started_at": _fmt(t.started_at), "finished_at": _fmt(t.finished_at),
                 "counter": t.counter.name if t.counter else "", "attendant": t.attendant.full_name if t.attendant else "",
                 "wait_min": _mins(t.created_at, t.called_at),
                 "service_min": _mins(t.started_at, t.finished_at) if t.status == "ATENDIDA" else None} for t in ts]
        data = {"columns": [{"key": k, "label": lb} for k, lb in cols], "rows": rows}
    elif kind == "summary":
        s = _stats(ts)
        labels = [("emitted", "Senhas emitidas"), ("attended", "Senhas atendidas"), ("priority", "Senhas prioritárias"),
                  ("normal", "Senhas normais"), ("no_show", "Não comparecimentos"), ("cancelled", "Canceladas"),
                  ("avg_wait_min", "Tempo médio de espera (min)"), ("avg_service_min", "Tempo médio de atendimento (min)")]
        data = {"columns": [{"key": "metric", "label": "Indicador"}, {"key": "value", "label": "Valor"}],
                "rows": [{"metric": lb, "value": s[k]} for k, lb in labels]}
    elif kind == "by_hour":
        data = _group_table(ts, lambda t: f"{_local(t.created_at).hour:02d}:00", "Hora")
    elif kind == "by_day":
        data = _group_table(ts, lambda t: t.service_date.strftime("%d/%m/%Y"), "Dia")
        data["rows"].sort(key=lambda r: datetime.strptime(r["group"], "%d/%m/%Y"))
    elif kind == "by_type":
        data = _group_table(ts, lambda t: t.ticket_type.name, "Tipo")
    elif kind == "by_attendant":
        data = _group_table([t for t in ts if t.attendant_id], lambda t: t.attendant.full_name, "Funcionário")
    elif kind == "by_counter":
        data = _group_table([t for t in ts if t.counter_id], lambda t: t.counter.name, "Guichê")
    else:
        data = _group_table(ts, lambda t: STATUS_LABEL[t.status], "Situação")
    data.update(kind=kind, title=KINDS[kind], count=len(data["rows"]))
    return data


# ---- exportação ------------------------------------------------------------
def _cell(v) -> str:
    return "" if v is None else str(v).replace(".", ",") if isinstance(v, float) else str(v)


def to_csv(data: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([c["label"] for c in data["columns"]])
    for r in data["rows"]:
        w.writerow([_safe_csv(_cell(r.get(c["key"]))) for c in data["columns"]])
    return buf.getvalue().encode("utf-8-sig")


def _safe_csv(s: str) -> str:
    """Evita injeção de fórmulas ao abrir no Excel."""
    return "'" + s if s[:1] in ("=", "+", "-", "@") and not s.replace(",", "").replace("-", "").isdigit() else s


def to_xlsx(data: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = data["title"][:31]
    ws.append([c["label"] for c in data["columns"]])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in data["rows"]:
        ws.append([_safe_csv(v) if isinstance(v, str) else v for v in (r.get(c["key"]) for c in data["columns"])])
    for i, c in enumerate(data["columns"], 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(12, len(c["label"]) + 2)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf(data: dict, subtitle: str = "") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    ss = getSampleStyleSheet()
    body = ss["BodyText"]
    body.fontSize = 7
    body.leading = 8
    story = [Paragraph(data["title"], ss["Title"]), Paragraph(subtitle or "", ss["Normal"]), Spacer(1, 8)]
    esc = lambda s: _cell(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    rows = [[Paragraph(f"<b>{esc(c['label'])}</b>", body) for c in data["columns"]]]
    for r in data["rows"]:
        rows.append([Paragraph(esc(r.get(c["key"])), body) for c in data["columns"]])
    tbl = Table(rows, repeatRows=1)
    tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                             ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(tbl)
    doc.build(story)
    return out.getvalue()


# ---- dashboard -------------------------------------------------------------
def dashboard(db: Session) -> dict:
    today = local_today()
    ts = fetch(db, {"date_from": today, "date_to": today})
    s = _stats(ts)
    by_hour = defaultdict(int)
    by_type: dict[str, dict] = {}
    for t in ts:
        by_hour[_local(t.created_at).hour] += 1
        e = by_type.setdefault(t.ticket_type.name, {"name": t.ticket_type.name, "color": t.ticket_type.color, "count": 0})
        e["count"] += 1
    attended_hour = defaultdict(int)
    for t in ts:
        if t.status == "ATENDIDA" and t.finished_at:
            attended_hour[_local(t.finished_at).hour] += 1
    hours = range(0, 24)
    return {
        "counts": counts_today(db), "avg_wait_min": s["avg_wait_min"], "avg_service_min": s["avg_service_min"],
        "priority_today": s["priority"],
        "by_hour": [{"hour": h, "issued": by_hour.get(h, 0), "attended": attended_hour.get(h, 0)} for h in hours],
        "by_type": sorted(by_type.values(), key=lambda x: -x["count"]),
        "oldest_waiting_min": _oldest_wait(ts),
    }


def _oldest_wait(ts: list[Ticket]) -> float | None:
    from ..db import utcnow
    w = [t.created_at for t in ts if t.status == "AGUARDANDO"]
    return round((utcnow() - min(w)).total_seconds() / 60, 1) if w else None
