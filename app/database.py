from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(database_url: str):
    options = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=options, future=True)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_sqlite_schema() -> None:
    """Add backward-compatible fields when starting against an earlier lab database."""
    if not engine.url.drivername.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "meetings" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("meetings")}
    with engine.begin() as connection:
        if "location" not in columns:
            connection.execute(text("ALTER TABLE meetings ADD COLUMN location VARCHAR(500)"))
        if "attendees" not in columns:
            connection.execute(text("ALTER TABLE meetings ADD COLUMN attendees JSON"))
