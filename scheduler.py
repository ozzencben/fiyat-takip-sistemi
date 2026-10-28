import argparse
import os
import sys

# src dizinini import yoluna ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from fiyat_takip_sistemi.scheduler import start_scheduler

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fiyat Takip Sistemi Zamanlayıcısı")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test için zamanlayıcıyı her 1 dakikada bir çalışacak şekilde başlatır.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Test sırasında belirtilen çalışma sayısından sonra zamanlayıcıyı durdurur.",
    )
    args = parser.parse_args()
    start_scheduler(test_mode=args.test, max_runs=args.max_runs)
