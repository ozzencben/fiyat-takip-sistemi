import os
import sys

# src dizinini import yoluna ekle (uvicorn api.main:app --reload uyumluluğu için)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.api.main import app  # noqa: F401

