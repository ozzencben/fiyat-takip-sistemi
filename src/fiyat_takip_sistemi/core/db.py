# core/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///fiyat_takip.db"

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI ve bağımsız scriptler için veritabanı oturum üreteci."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()