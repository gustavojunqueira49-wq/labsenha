"""Renderização da senha em ESC/POS (impressoras térmicas Epson/Bematech/Elgin/Daruma...)."""
from __future__ import annotations

import textwrap
from datetime import datetime

from ..config import config

ESC, GS = b"\x1b", b"\x1d"
CODEPAGES = {"cp437": 0, "cp850": 2, "cp860": 3, "cp858": 19, "cp1252": 16}


def _fmt_dt(iso: str | None) -> tuple[str, str]:
    dt = datetime.fromisoformat(iso) if iso else datetime.now(config.tz)
    dt = dt.astimezone(config.tz)
    return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")


def build_lines(payload: dict, st: dict) -> list[dict]:
    """Layout lógico (independente do hardware): lista de {text, align, bold, size}.
    Serve tanto para ESC/POS quanto para o modo texto do agente e para pré-visualização."""
    date_s, time_s = _fmt_dt(payload.get("issued_at"))
    L: list[dict] = []

    def add(text="", align="center", bold=False, size=1):
        L.append({"text": text, "align": align, "bold": bold, "size": size})

    if payload.get("kind") == "TEST":
        add(st["hospital.name"], bold=True, size=2)
        add("TESTE DE IMPRESSAO", bold=True)
        add("")
        add("Impressora funcionando!")
        add(f"{date_s} {time_s}")
        return L
    add(st["hospital.name"], bold=True, size=2)
    add(st["lab.name"], bold=True)
    if st.get("ticket.header"):
        add(st["ticket.header"])
    add("")
    label = payload.get("category_name") or payload.get("type_name") or ""
    add(label.upper(), bold=True)
    add("")
    add(payload["code"], bold=True, size=-1)  # -1 = "tamanho da senha" (definido pela impressora)
    add("")
    if st.get("ticket.message"):
        add(st["ticket.message"], bold=True)
    add("")
    add(date_s)
    add(time_s)
    if st.get("ticket.footer"):
        add("")
        add(st["ticket.footer"])
    return L


def render_text(lines: list[dict], width: int) -> str:
    out = []
    for ln in lines:
        w = max(8, width // (ln["size"] if ln["size"] > 0 else 3))
        for part in (textwrap.wrap(ln["text"], w) or [""]):
            out.append(part.center(width) if ln["align"] == "center" else part)
    return "\n".join(out)


def render_escpos(lines: list[dict], printer) -> bytes:
    enc = printer.encoding if printer.encoding in CODEPAGES else "cp850"
    cpl = printer.chars_per_line
    b = bytearray(ESC + b"@")  # init
    b += ESC + b"t" + bytes([CODEPAGES[enc]])
    b += ESC + b"d" + bytes([max(0, printer.margin_top)])
    for ln in lines:
        size = printer.code_size if ln["size"] == -1 else ln["size"]
        size = max(1, min(8, size))
        b += ESC + b"a" + (b"\x01" if ln["align"] == "center" else b"\x00")
        b += ESC + b"E" + (b"\x01" if ln["bold"] else b"\x00")
        b += GS + b"!" + bytes([((size - 1) << 4) | (size - 1)])
        width = max(6, cpl // size)
        for part in (textwrap.wrap(ln["text"], width) or [""]):
            b += part.encode(enc, errors="replace") + b"\n"
    b += GS + b"!\x00" + ESC + b"E\x00" + ESC + b"a\x00"
    b += ESC + b"d" + bytes([max(0, printer.margin_bottom)])
    if printer.cut:
        b += GS + b"V\x42\x00"  # corte parcial com avanço
    return bytes(b)
