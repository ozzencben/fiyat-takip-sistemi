import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.core.db import SessionLocal
from fiyat_takip_sistemi.core.matching import run_product_matching

if __name__ == "__main__":
    session = SessionLocal()
    try:
        run_product_matching(session)
    finally:
        session.close()

