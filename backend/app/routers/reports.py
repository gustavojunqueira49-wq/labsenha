from __future__ import annotations

from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Auth, require
from ..models import User
from ..services import backup as backup_svc
from ..services import reports as svc

router = APIRouter(tags=["Relatórios e dashboard"])


def _filters(date_from: date | None, date_to: date | None, time_from: time | None, time_to: time | None,
             type_id: int | None, attendant_id: int | None, counter_id: int | None, status: str | None) -> dict:
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "Data final anterior à inicial.")
    if date_from and date_to and (date_to - date_from).days > 366:
        raise HTTPException(422, "Período máximo: 366 dias.")
    return dict(date_from=date_from, date_to=date_to, time_from=time_from, time_to=time_to, type_id=type_id,
                attendant_id=attendant_id, counter_id=counter_id, status=status.upper() if status else None)


@router.get("/dashboard")
def dashboard(auth: Auth = Depends(require("dashboard.view")), db: Session = Depends(get_db)):
    d = svc.dashboard(db)
    d["backup"] = backup_svc.status(db)
    return d


@router.get("/reports")
def report_kinds(auth: Auth = Depends(require("reports.view"))):
    return {"kinds": [{"key": k, "label": v} for k, v in svc.KINDS.items()]}


@router.get("/reports/attendants")
def attendants(auth: Auth = Depends(require("reports.view")), db: Session = Depends(get_db)):
    return [{"id": u.id, "name": u.full_name} for u in db.scalars(select(User).order_by(User.full_name))]


@router.get("/reports/{kind}")
def report(kind: str, date_from: date | None = None, date_to: date | None = None, time_from: time | None = None,
           time_to: time | None = None, type_id: int | None = None, attendant_id: int | None = None,
           counter_id: int | None = None, status: str | None = None,
           auth: Auth = Depends(require("reports.view")), db: Session = Depends(get_db)):
    f = _filters(date_from, date_to, time_from, time_to, type_id, attendant_id, counter_id, status)
    try:
        return svc.build(db, kind, f)
    except KeyError:
        raise HTTPException(404, "Relatório desconhecido.") from None


@router.get("/reports/{kind}/export")
def export(kind: str, format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"), date_from: date | None = None,
           date_to: date | None = None, time_from: time | None = None, time_to: time | None = None,
           type_id: int | None = None, attendant_id: int | None = None, counter_id: int | None = None,
           status: str | None = None, auth: Auth = Depends(require("reports.export")), db: Session = Depends(get_db)):
    f = _filters(date_from, date_to, time_from, time_to, type_id, attendant_id, counter_id, status)
    try:
        data = svc.build(db, kind, f)
    except KeyError:
        raise HTTPException(404, "Relatório desconhecido.") from None
    audit(db, auth.user, "relatorio.exportado", "report", kind, {"format": format}, auth.ip)
    db.commit()
    name = f"relatorio_{kind}_{(f['date_from'] or date.today()).isoformat()}.{format}"
    if format == "csv":
        body, mime = svc.to_csv(data), "text/csv; charset=utf-8"
    elif format == "xlsx":
        body, mime = svc.to_xlsx(data), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        sub = f"Período: {f['date_from'] or 'hoje'} a {f['date_to'] or f['date_from'] or 'hoje'}"
        body, mime = svc.to_pdf(data, sub), "application/pdf"
    return Response(body, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})
