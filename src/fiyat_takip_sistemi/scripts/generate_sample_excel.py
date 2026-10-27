import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
EXCEL_PATH = DATA_DIR / "urunlerim.xlsx"

# books.toscrape.com'daki gerçek kitaplar baz alınarak hazırlandı.
# Eşleştirme algoritmasını (rapidfuzz) test etmek için bazı isimler hafifçe manipüle edildi.
SAMPLE_PRODUCTS = [
    {
        "sku": "BK-001",
        "urun_adi": "A Light in the Attic (Ciltli)",  # Sitede: A Light in the Attic
        "fiyat": 2100.0,
        "maliyet": 1400.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-002",
        "urun_adi": "Tipping the Velvet",  # Birebir aynı
        "fiyat": 2150.0,
        "maliyet": 1500.0,
        "min_marj_yuzde": 25.0,
    },
    {
        "sku": "BK-003",
        "urun_adi": "Soumission",  # Birebir aynı
        "fiyat": 2000.0,
        "maliyet": 1300.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-004",
        "urun_adi": "Sharp Objects - Roman",  # Sitede: Sharp Objects
        "fiyat": 1900.0,
        "maliyet": 1200.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-005",
        "urun_adi": "Sapiens: A Brief History",  # Sitede: Sapiens: A Brief History of Humankind
        "fiyat": 2200.0,
        "maliyet": 1600.0,
        "min_marj_yuzde": 15.0,
    },
    {
        "sku": "BK-006",
        "urun_adi": "The Requiem Red",
        "fiyat": 900.0,
        "maliyet": 600.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-007",
        "urun_adi": "The Dirty Little Secrets of Getting Your Dream Job",
        "fiyat": 1350.0,
        "maliyet": 900.0,
        "min_marj_yuzde": 25.0,
    },
    {
        "sku": "BK-008",
        "urun_adi": "The Coming Woman: A Novel",  # Sitede: The Coming Woman: A Novel Based on the Life of the Infamous Feminist, Victoria Woodhull
        "fiyat": 750.0,
        "maliyet": 500.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-009",
        "urun_adi": "The Boys in the Boat",  # Sitede: The Boys in the Boat: Nine Americans and Their Epic Quest for Gold at the 1936 Berlin Olympics
        "fiyat": 950.0,
        "maliyet": 650.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-010",
        "urun_adi": "The Black Maria",
        "fiyat": 2100.0,
        "maliyet": 1450.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-011",
        "urun_adi": "Starving Hearts (Triangular Trade Trilogy)",  # Sitede: Starving Hearts (Triangular Trade Trilogy, #1)
        "fiyat": 550.0,
        "maliyet": 350.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-012",
        "urun_adi": "Shakespeare's Sonnets",
        "fiyat": 850.0,
        "maliyet": 550.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-013",
        "urun_adi": "Set Me Free",
        "fiyat": 700.0,
        "maliyet": 450.0,
        "min_marj_yuzde": 25.0,
    },
    {
        "sku": "BK-014",
        "urun_adi": "Scott Pilgrim's Precious Little Life",  # Sitede: Scott Pilgrim's Precious Little Life (Scott Pilgrim #1)
        "fiyat": 2100.0,
        "maliyet": 1400.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-015",
        "urun_adi": "Rip it Up and Start Again",
        "fiyat": 1400.0,
        "maliyet": 950.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-016",
        "urun_adi": "Our Band Could Be Your Life",  # Sitede: Our Band Could Be Your Life: Scenes from the American Indie Underground, 1981-1991
        "fiyat": 2300.0,
        "maliyet": 1600.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-017",
        "urun_adi": "Olio Şiir Kitabı",  # Sitede: Olio
        "fiyat": 950.0,
        "maliyet": 600.0,
        "min_marj_yuzde": 25.0,
    },
    {
        "sku": "BK-018",
        "urun_adi": "Mesa Selimovic - Death and the Dervish",  # Sitede: Death and the Dervish
        "fiyat": 750.0,
        "maliyet": 500.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-019",
        "urun_adi": "Frankenstein",  # Birebir aynı
        "fiyat": 1550.0,
        "maliyet": 1000.0,
        "min_marj_yuzde": 25.0,
    },
    {
        "sku": "BK-020",
        "urun_adi": "Forever and Forever",  # Sitede: Forever and Forever: The Courtship of Henry Longfellow and Fanny Appleton
        "fiyat": 1200.0,
        "maliyet": 800.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-021",
        "urun_adi": "Emma",
        "fiyat": 1350.0,
        "maliyet": 900.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-022",
        "urun_adi": "Alice in Wonderland",  # Sitede: Alice's Adventures in Wonderland
        "fiyat": 2250.0,
        "maliyet": 1500.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-023",
        "urun_adi": "Ajin: Demi-Human, Volume 1",
        "fiyat": 1750.0,
        "maliyet": 1150.0,
        "min_marj_yuzde": 25.0,
    },
    {
        "sku": "BK-024",
        "urun_adi": "A Spy's Alone",
        "fiyat": 2050.0,
        "maliyet": 1350.0,
        "min_marj_yuzde": 20.0,
    },
    {
        "sku": "BK-025",
        "urun_adi": "1,000 Places to See Before You Die",
        "fiyat": 1100.0,
        "maliyet": 750.0,
        "min_marj_yuzde": 20.0,
    },
]


def create_excel() -> None:
    df = pd.DataFrame(SAMPLE_PRODUCTS)
    df.to_excel(EXCEL_PATH, index=False)
    print(f"✓ {len(df)} ürün başarıyla '{EXCEL_PATH}' dosyasına kaydedildi.")


if __name__ == "__main__":
    create_excel()