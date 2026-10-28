import os
import random
import sys

# src dizinini import yoluna ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.scripts.simulate_price_change import simulate_price_drop

if __name__ == "__main__":
    count = random.choice([5, 6])
    simulate_price_drop(count)
