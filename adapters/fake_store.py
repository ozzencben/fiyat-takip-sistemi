import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.adapters.fake_store import (
    FakeStoreAdapter,
    save_snapshots_to_db,
)
from fiyat_takip_sistemi.core.db import SessionLocal

if __name__ == "__main__":
    adapter = FakeStoreAdapter()
    try:
        scraped = adapter.fetch_products()
        session = SessionLocal()
        try:
            saved = save_snapshots_to_db(session, scraped)
            print(f"✓ price_snapshots tablosuna {saved} yeni Rakip C kaydı yazıldı.")
        finally:
            session.close()
    finally:
        adapter.close()
