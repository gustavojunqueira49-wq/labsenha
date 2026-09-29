"""Configurações de negócio, com valores padrão e metadados para a tela de administração."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Setting


@dataclass(frozen=True)
class Def:
    key: str
    default: object
    type: str  # string | text | int | bool | logo
    group: str
    label: str
    help: str = ""
    min: int | None = None
    max: int | None = None


DEFS: list[Def] = [
    # Hospital
    Def("hospital.name", "HOSPITAL EXEMPLO", "string", "Hospital", "Nome do hospital"),
    Def("lab.name", "LABORATÓRIO", "string", "Hospital", "Nome do laboratório"),
    Def("hospital.address", "", "string", "Hospital", "Endereço"),
    Def("hospital.phone", "", "string", "Hospital", "Telefone"),
    Def("hospital.logo", "", "logo", "Hospital", "Logo (exibida no painel e nas telas)",
        "Imagem PNG/JPG pequena (até ~200 KB). Não é impressa na senha térmica."),
    # Senha
    Def("ticket.header", "", "string", "Senha impressa", "Cabeçalho extra",
        "Linha opcional abaixo do nome do laboratório."),
    Def("ticket.message", "AGUARDE SER CHAMADO", "string", "Senha impressa", "Mensagem da senha"),
    Def("ticket.footer", "", "string", "Senha impressa", "Rodapé"),
    Def("ticket.digits", 3, "int", "Senha impressa", "Dígitos da numeração", "Ex.: 3 → N001", 1, 6),
    Def("ticket.separator", "", "string", "Senha impressa", "Separador entre prefixo e número",
        "Vazio → N001 · '-' → N-001"),
    Def("print.auto", True, "bool", "Senha impressa", "Imprimir automaticamente ao gerar a senha"),
    Def("print.max_attempts", 20, "int", "Senha impressa", "Tentativas automáticas de impressão",
        "Depois disso o trabalho fica em ERRO até ser reenviado manualmente (nunca é apagado).", 1, 1000),
    # Painel
    Def("panel.message", "Dirija-se ao local indicado quando sua senha for chamada.", "string", "Painel",
        "Mensagem do painel"),
    Def("panel.show_history", 6, "int", "Painel", "Quantidade de últimas chamadas", "", 1, 12),
    # Áudio
    Def("audio.enabled", True, "bool", "Áudio", "Som ao chamar"),
    Def("audio.chime", True, "bool", "Áudio", "Tocar sinal sonoro (bip)"),
    Def("audio.voice", True, "bool", "Áudio", "Anunciar por voz sintetizada"),
    Def("audio.template", "Senha {senha}, dirigir-se à {guiche}.", "string", "Áudio",
        "Frase falada", "Use {senha} e {guiche}."),
    Def("audio.lang", "pt-BR", "string", "Áudio", "Idioma da voz"),
    Def("audio.rate", 90, "int", "Áudio", "Velocidade da voz (%)", "", 50, 150),
    Def("audio.repeat", 2, "int", "Áudio", "Repetições da frase", "", 1, 3),
    # Fila
    Def("queue.reset_daily", True, "bool", "Regras da fila", "Reiniciar numeração todo dia"),
    Def("queue.max_consecutive_priority", 3, "int", "Regras da fila",
        "Máx. de prioritárias seguidas antes de chamar uma comum",
        "0 = prioridade estrita (a fila comum só anda quando não há prioritárias). "
        "Definir com validação da área jurídica/administrativa do hospital.", 0, 100),
    Def("queue.aging_minutes", 45, "int", "Regras da fila",
        "Tempo máx. de espera da fila comum (minutos)",
        "Senha comum que esperar mais que isso passa à frente. 0 = desligado.", 0, 1440),
    Def("queue.recall_limit", 3, "int", "Regras da fila", "Rechamadas antes de sugerir 'Não compareceu'", "", 0, 20),
    # Segurança
    Def("session.idle_minutes", 480, "int", "Segurança", "Expiração da sessão por inatividade (min)",
        "Usuários do perfil PAINEL não expiram por inatividade.", 5, 10080),
    Def("security.max_failed_logins", 5, "int", "Segurança", "Tentativas de login antes de bloquear", "", 3, 20),
    Def("security.lockout_minutes", 15, "int", "Segurança", "Minutos de bloqueio após tentativas", "", 1, 1440),
    # Backup
    Def("backup.auto_enabled", True, "bool", "Backup", "Backup automático"),
    Def("backup.interval_hours", 24, "int", "Backup", "Intervalo do backup automático (horas)", "", 1, 720),
    Def("backup.keep", 30, "int", "Backup", "Quantidade de backups automáticos mantidos", "", 1, 1000),
    Def("backup.alert_hours", 36, "int", "Backup", "Alertar se o último backup for mais antigo que (horas)", "", 1, 10000),
    Def("backup.dir", "", "string", "Backup", "Diretório dos backups", "Vazio = padrão do servidor (.env BACKUP_DIR)."),
]
DEF_MAP = {d.key: d for d in DEFS}


def get_all(db: Session) -> dict:
    values = {d.key: d.default for d in DEFS}
    for row in db.query(Setting).all():
        if row.key in values:
            values[row.key] = row.value
    return values


def get(db: Session, key: str):
    row = db.get(Setting, key)
    return row.value if row is not None else DEF_MAP[key].default


def coerce(d: Def, value):
    if d.type == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError(f"'{d.label}' deve ser verdadeiro/falso")
    if d.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"'{d.label}' deve ser um número inteiro") from None
        if d.min is not None and value < d.min or d.max is not None and value > d.max:
            raise ValueError(f"'{d.label}' deve estar entre {d.min} e {d.max}")
        return value
    if not isinstance(value, str):
        raise ValueError(f"'{d.label}' deve ser texto")
    if d.type == "logo":
        if value and (not value.startswith("data:image/") or len(value) > 400_000):
            raise ValueError("Logo inválida (use imagem pequena, até ~200 KB)")
        return value
    if len(value) > 500:
        raise ValueError(f"'{d.label}' é muito longo")
    return value.strip()


def public_view(values: dict) -> dict:
    """Subconjunto exposto a qualquer usuário autenticado (painel, telas)."""
    keys = [
        "hospital.name", "lab.name", "hospital.logo", "panel.message", "panel.show_history",
        "audio.enabled", "audio.chime", "audio.voice", "audio.template", "audio.lang",
        "audio.rate", "audio.repeat", "queue.recall_limit", "session.idle_minutes",
    ]
    return {k: values[k] for k in keys}
