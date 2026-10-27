"""Banco de dados (SQLAlchemy + Alembic): usuários, sessões e dono de cada livro.
Postgres em produção (DATABASE_URL); sem a variável, usa SQLite em AUDIOPDF_DATA/audiopdf.db."""
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_lock = threading.RLock()
_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None
_ready = False


def default_url() -> str:
    """AUDIOPDF_DB=sqlite força o SQLite em AUDIOPDF_DATA mesmo com DATABASE_URL definida (contingência se o Postgres estiver inacessível)."""
    url = os.environ.get("DATABASE_URL")
    if url and os.environ.get("AUDIOPDF_DB", "").lower() != "sqlite":
        return url
    data = Path(os.environ.get("AUDIOPDF_DATA", "data")).resolve()
    data.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{data / 'audiopdf.db'}"


def configure(url: str | None = None) -> Engine:
    """(Re)cria o engine. Os testes chamam com uma URL própria."""
    global _engine, _factory, _ready
    with _lock:
        if _engine is not None:
            _engine.dispose()
        url = url or default_url()
        kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _fk(conn, _):  # SQLite só respeita chave estrangeira com o PRAGMA
                conn.execute("PRAGMA foreign_keys=ON")
        _factory = sessionmaker(_engine, expire_on_commit=False)
        _ready = False
        return _engine


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.attributes["engine"] = engine()
    command.upgrade(cfg, "head")


def engine() -> Engine:
    return _engine or configure()


def init() -> None:
    """Aplica as migrations uma vez por processo (idempotente)."""
    global _ready
    if _ready:
        return
    with _lock:
        if not _ready:
            migrate()
            _ready = True


@contextmanager
def session() -> Iterator[Session]:
    init()
    engine()
    assert _factory is not None
    s = _factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
