import os
import sys

# src dizinini import yoluna ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.core.db import SessionLocal
from fiyat_takip_sistemi.scripts.seed_history import seed_price_history

if __name__ == "__main__":
    session = SessionLocal()
    try:
        seed_price_history(session, days=14)
    finally:
        session.close()
