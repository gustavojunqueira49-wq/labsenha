#!/usr/bin/env python
"""Agente de impressão — Fila de Senhas (Laboratório).

Roda no computador ligado à impressora térmica (USB) e:
  1. conecta ao servidor pela rede local (HTTP, sem internet);
  2. busca senhas pendentes (a cada ~1,5 s, isso também serve de "sinal de vida");
  3. imprime em modo RAW (ESC/POS) na impressora do Windows, TCP 9100, CUPS ou arquivo (testes);
  4. informa ao servidor: impresso / erro / sem papel / impressora desligada.

A fila de impressão fica no BANCO do servidor: se o agente ou a impressora ficarem fora do ar,
nenhuma senha se perde — tudo é impresso quando voltarem.

Somente biblioteca padrão (+ pywin32 no Windows para o modo "windows").
"""
from __future__ import annotations

import argparse
import base64
import configparser
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path

__version__ = "1.0.0"
HERE = Path(__file__).resolve().parent
log = logging.getLogger("print-agent")

# bits de PRINTER_INFO.Status (winspool.h)
WIN_STATUS = [
    (0x00000010, "SEM_PAPEL", "Sem papel"), (0x00000008, "ERRO", "Papel enroscado"),
    (0x00000020, "SEM_PAPEL", "Problema de papel"), (0x00000080, "OFFLINE", "Impressora offline"),
    (0x00001000, "OFFLINE", "Impressora indisponível"), (0x00400000, "ERRO", "Tampa aberta"),
    (0x00040000, "ERRO", "Requer intervenção do usuário"), (0x00000002, "ERRO", "Erro na impressora"),
    (0x00000400, "OFFLINE", "Impressora desligada"),
]


class PrintError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# ---- backends de impressão -----------------------------------------------------------
class WindowsBackend:
    def __init__(self, name: str):
        try:
            import win32print  # type: ignore
        except ImportError:
            sys.exit("Modo 'windows' requer pywin32:  pip install pywin32")
        self.w, self.name = win32print, name or win32print.GetDefaultPrinter()

    def status(self) -> tuple[str, str | None]:
        try:
            h = self.w.OpenPrinter(self.name)
        except Exception as e:  # impressora inexistente / removida
            return "OFFLINE", f"Não foi possível abrir '{self.name}': {e}"
        try:
            st = self.w.GetPrinter(h, 2)["Status"]
        finally:
            self.w.ClosePrinter(h)
        for bit, code, txt in WIN_STATUS:
            if st & bit:
                return code, txt
        return "ONLINE", None

    def send(self, data: bytes) -> None:
        w = self.w
        try:
            h = w.OpenPrinter(self.name)
        except Exception as e:
            raise PrintError("OFFLINE", f"Impressora '{self.name}' indisponível: {e}") from e
        try:
            w.StartDocPrinter(h, 1, ("Senha", None, "RAW"))
            try:
                w.StartPagePrinter(h)
                w.WritePrinter(h, data)
                w.EndPagePrinter(h)
            finally:
                w.EndDocPrinter(h)
        except Exception as e:
            raise PrintError("ERRO", f"Falha ao enviar para a impressora: {e}") from e
        finally:
            w.ClosePrinter(h)


class TcpBackend:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port

    def status(self):
        try:
            socket.create_connection((self.host, self.port), timeout=2).close()
            return "ONLINE", None
        except OSError as e:
            return "OFFLINE", f"{self.host}:{self.port} — {e}"

    def send(self, data: bytes) -> None:
        try:
            with socket.create_connection((self.host, self.port), timeout=5) as s:
                s.sendall(data)
        except OSError as e:
            raise PrintError("OFFLINE", f"Impressora de rede indisponível: {e}") from e


class CupsBackend:
    def __init__(self, name: str):
        self.name = name

    def status(self):
        r = subprocess.run(["lpstat", "-p", self.name], capture_output=True, text=True)
        if r.returncode != 0:
            return "OFFLINE", (r.stderr or r.stdout).strip()[:200]
        return ("OFFLINE", r.stdout.strip()[:200]) if "disabled" in r.stdout else ("ONLINE", None)

    def send(self, data: bytes) -> None:
        r = subprocess.run(["lp", "-d", self.name, "-o", "raw"], input=data, capture_output=True)
        if r.returncode != 0:
            raise PrintError("ERRO", r.stderr.decode(errors="replace")[:300])


class FileBackend:
    """Para testes sem impressora: grava os bytes em arquivos."""

    def __init__(self, folder: str):
        self.dir = Path(folder or HERE / "spool")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.n = 0

    def status(self):
        return "ONLINE", None

    def send(self, data: bytes) -> None:
        self.n += 1
        (self.dir / f"senha_{int(time.time() * 1000)}_{self.n}.bin").write_bytes(data)


def make_backend(cfg: configparser.ConfigParser):
    mode = cfg.get("printer", "mode", fallback="windows").lower()
    if mode == "windows":
        return WindowsBackend(cfg.get("printer", "name", fallback=""))
    if mode == "tcp":
        return TcpBackend(cfg.get("printer", "host"), cfg.getint("printer", "port", fallback=9100))
    if mode == "cups":
        return CupsBackend(cfg.get("printer", "name"))
    if mode == "file":
        return FileBackend(cfg.get("printer", "folder", fallback=""))
    sys.exit(f"printer.mode inválido: {mode}")


# ---- agente ---------------------------------------------------------------------------
class Agent:
    def __init__(self, cfg: configparser.ConfigParser, backend=None, state_file: Path | None = None):
        self.cfg = cfg
        self.url = cfg.get("server", "url").rstrip("/")
        self.token = cfg.get("server", "token")
        self.poll = cfg.getfloat("agent", "poll_seconds", fallback=1.5)
        self.backend = backend or make_backend(cfg)
        self.printer_name = cfg.get("printer", "name", fallback=cfg.get("printer", "mode", fallback=""))
        self.state_file = state_file or HERE / "agent_state.json"
        self.state = self._load_state()
        self.connected = None

    # estado local: evita imprimir duas vezes se o servidor reenviar um job cujo resultado se perdeu
    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return {"printed": [], "unreported": []}

    def _save_state(self) -> None:
        self.state["printed"] = self.state["printed"][-500:]
        try:
            self.state_file.write_text(json.dumps(self.state))
        except OSError:
            log.warning("Não foi possível gravar %s", self.state_file)

    def api(self, path: str, payload: dict, timeout: float = 8.0) -> dict:
        req = urllib.request.Request(
            self.url + "/api/agent" + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-Agent-Token": self.token}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")

    def base_info(self, status: str, detail: str | None) -> dict:
        return {"version": __version__, "hostname": platform.node(), "printer_name": self.printer_name,
                "printer_status": status, "printer_detail": detail}

    def report(self, job_id: int, ok: bool, error: str | None, status: str | None) -> bool:
        try:
            self.api(f"/jobs/{job_id}/result", {"ok": ok, "error": error, "printer_status": status})
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:  # job não é mais nosso: descarta
                return True
            return False
        except Exception:
            return False

    def flush_unreported(self) -> None:
        keep = []
        for r in self.state["unreported"]:
            if not self.report(r["id"], r["ok"], r.get("error"), r.get("status")):
                keep.append(r)
        if len(keep) != len(self.state["unreported"]):
            self.state["unreported"] = keep
            self._save_state()

    def handle(self, job: dict) -> None:
        jid = job["id"]
        if jid in self.state["printed"]:  # já impresso antes (resultado não chegou ao servidor)
            log.info("Job %s já impresso anteriormente; apenas confirmando.", jid)
            self.state["unreported"].append({"id": jid, "ok": True})
            return
        try:
            self.backend.send(base64.b64decode(job["escpos_b64"]))
        except PrintError as e:
            log.error("Job %s falhou: %s", jid, e.message)
            if not self.report(jid, False, e.message, e.status):
                self.state["unreported"].append({"id": jid, "ok": False, "error": e.message, "status": e.status})
            return
        log.info("Senha %s impressa (job %s)", job.get("code") or job["kind"], jid)
        self.state["printed"].append(jid)
        self._save_state()  # grava ANTES de reportar
        if not self.report(jid, True, None, "ONLINE"):
            self.state["unreported"].append({"id": jid, "ok": True})

    def step(self) -> int:
        """Um ciclo: retorna quantidade de jobs processados."""
        status, detail = self.backend.status()
        try:
            self.flush_unreported()
            resp = self.api("/jobs/claim", self.base_info(status, detail))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                log.error("Token inválido — confira config.ini")
            else:
                log.warning("Servidor respondeu %s", e.code)
            self.connected = False
            return 0
        except Exception as e:
            if self.connected is not False:
                log.warning("Sem conexão com o servidor (%s). Tentando novamente...", e)
            self.connected = False
            return 0
        if self.connected is not True:
            log.info("Conectado ao servidor %s", self.url)
        self.connected = True
        jobs = resp.get("jobs", [])
        for job in jobs:
            self.handle(job)
        self._save_state()
        return len(jobs)

    def run(self) -> None:
        log.info("Agente %s iniciado — servidor %s", __version__, self.url)
        while True:
            try:
                n = self.step()
            except Exception:
                log.exception("Erro inesperado no ciclo")
                n = 0
            time.sleep(0 if n else self.poll)


def setup_logging(verbose: bool) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = RotatingFileHandler(HERE / "agent.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stdout is not None:  # pythonw não tem console
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


def main() -> None:
    ap = argparse.ArgumentParser(description="Agente de impressão da Fila de Senhas")
    ap.add_argument("-c", "--config", default=str(HERE / "config.ini"))
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--once", action="store_true", help="processa um ciclo e sai (diagnóstico)")
    args = ap.parse_args()
    setup_logging(args.verbose)
    cfg = configparser.ConfigParser()
    if not cfg.read(args.config, encoding="utf-8"):
        sys.exit(f"Arquivo de configuração não encontrado: {args.config} (copie config.ini.example)")
    agent = Agent(cfg)
    if args.once:
        print("jobs processados:", agent.step())
    else:
        agent.run()


if __name__ == "__main__":
    main()
