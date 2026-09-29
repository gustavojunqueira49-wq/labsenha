from alembic import context

from app import models  # noqa: F401  (registra as tabelas)
from app.config import config as app_config
from app.db import Base, make_engine

target_metadata = Base.metadata


def run_migrations() -> None:
    engine = make_engine(app_config.database_url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata,
                          render_as_batch=app_config.is_sqlite, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
