import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.core.db import SessionLocal
from fiyat_takip_sistemi.core.load_excel import load_products_from_excel
from fiyat_takip_sistemi.core.models import Product

if __name__ == "__main__":
    session = SessionLocal()
    try:
        count = load_products_from_excel(session)
        total_in_db = session.query(Product).count()
        print(f"✓ Excel işlendi: {count} satır.")
        print(f"✓ Veritabanındaki güncel toplam ürün: {total_in_db}")
    finally:
        session.close()
