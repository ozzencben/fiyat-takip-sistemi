import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.core.db import SessionLocal
from fiyat_takip_sistemi.core.report import run_daily_report

if __name__ == "__main__":
    session = SessionLocal()
    try:
        run_daily_report(session)
    finally:
        session.close()
