import os
import sys

# src dizinini import yoluna ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from fiyat_takip_sistemi.run_daily import main

if __name__ == "__main__":
    main()
