import os
import sys

# src dizinini import yoluna ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.scripts.demo_reset import reset_demo_state

if __name__ == "__main__":
    reset_demo_state()

