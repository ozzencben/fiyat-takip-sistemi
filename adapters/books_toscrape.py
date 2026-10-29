import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.adapters.books_toscrape import (
    BooksToScrapeAdapter,
    save_snapshots_to_db,
)
from fiyat_takip_sistemi.core.db import SessionLocal

if __name__ == "__main__":
    adapter = BooksToScrapeAdapter()
    try:
        scraped = adapter.fetch_products(max_pages=5)
        session = SessionLocal()
        try:
            saved_count = save_snapshots_to_db(session, scraped)
            print(f"✓ price_snapshots tablosuna {saved_count} yeni kayıt yazıldı.")
        finally:
            session.close()
    finally:
        adapter.close()
