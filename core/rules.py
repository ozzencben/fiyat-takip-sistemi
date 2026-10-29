import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.core.db import SessionLocal
from fiyat_takip_sistemi.core.rules import evaluate_rules, print_alerts_summary

if __name__ == "__main__":
    session = SessionLocal()
    try:
        active_alerts = evaluate_rules(session)
        print_alerts_summary(active_alerts)
    finally:
        session.close()

