"""
Datenbankverbindung und Session Management
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from ...config import settings

# Datenbank-Engine erstellen
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Verbindung vor Nutzung prüfen
    pool_recycle=3600,   # Verbindung nach 1 Stunde erneuern
    echo=settings.debug  # SQL-Logging nur im Debug-Modus
)

# Session-Factory erstellen
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Generator für Datenbank-Sessions.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()