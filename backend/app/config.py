"""Configuração de infraestrutura (variáveis de ambiente / arquivo .env).

Parâmetros de negócio (nome do hospital, regras da fila, som...) ficam na
tabela `settings` e são editados pela tela de Administração.
"""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # postgresql+psycopg://usuario:senha@localhost:5432/senhas_lab
    database_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'dev.db'}"
    host: str = "0.0.0.0"
    port: int = 8000
    timezone: str = "America/Sao_Paulo"
    data_dir: Path = ROOT_DIR / "data"
    backup_dir: Path = ROOT_DIR / "backups"
    frontend_dir: Path = ROOT_DIR / "frontend"
    # Se vazio, uma senha aleatória é gerada no primeiro start.
    initial_admin_password: str = ""
    initial_admin_username: str = "administrador"
    # Ligue apenas se houver HTTPS na frente (ex.: proxy reverso)
    cookie_secure: bool = False
    cors_origins: str = ""  # lista separada por vírgula; vazio = mesma origem
    maintenance_interval_seconds: int = 5
    disable_background_tasks: bool = False
    pg_bin_dir: str = ""  # pasta com pg_dump/pg_restore/psql (Windows)

    @field_validator("data_dir", "backup_dir", "frontend_dir", mode="after")
    @classmethod
    def _abs(cls, v: Path) -> Path:
        return v if v.is_absolute() else ROOT_DIR / v  # caminhos relativos partem da raiz do projeto

    @field_validator("database_url", mode="after")
    @classmethod
    def _sqlite_abs(cls, v: str) -> str:
        if v.startswith("sqlite:///") and not v.startswith("sqlite:////") and ":memory:" not in v:
            rel = v[len("sqlite:///"):]
            if not (len(rel) > 1 and rel[1] == ":"):  # não é "C:\..."
                return f"sqlite:///{ROOT_DIR / rel}"
        return v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


config = Config()
