import sys
from pathlib import Path
import pandas as pd
from sqlalchemy.orm import Session

# Windows konsolunda Türkçe ve Unicode karakterlerin düzgün yazdırılabilmesi için
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .db import SessionLocal
from .models import Product

# Proje kök dizinini ve varsayılan dosya yolunu dinamik bul
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXCEL_FILE = PROJECT_ROOT / "data" / "urunlerim.xlsx"


def load_products_from_excel(db: Session, file_path: Path | None = None) -> int:
    """Excel dosyasını okuyup products tablosuna idempotent şekilde aktarır."""
    if file_path is None:
        if Path("data/urunlerim.xlsx").exists():
            file_path = Path("data/urunlerim.xlsx")
        else:
            file_path = DEFAULT_EXCEL_FILE

    if not file_path.exists():
        raise FileNotFoundError(f"Excel dosyası bulunamadı: {file_path}")

    df = pd.read_excel(file_path)

    # Gerekli sütun kontrolü
    required_columns = {"sku", "urun_adi", "fiyat", "maliyet", "min_marj_yuzde"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Excel dosyasında eksik sütunlar var: {missing}")

    records_processed = 0

    for _, row in df.iterrows():
        sku_val = str(row["sku"]).strip()
        urun_adi_val = str(row["urun_adi"]).strip()
        fiyat_val = float(row["fiyat"])
        maliyet_val = float(row["maliyet"])
        min_marj_val = float(row["min_marj_yuzde"])

        # SKU bazlı kontrol (Idempotent update/insert)
        existing_product = db.query(Product).filter(Product.sku == sku_val).first()

        if existing_product:
            existing_product.urun_adi = urun_adi_val
            existing_product.fiyat = fiyat_val
            existing_product.maliyet = maliyet_val
            existing_product.min_marj_yuzde = min_marj_val
        else:
            new_product = Product(
                sku=sku_val,
                urun_adi=urun_adi_val,
                fiyat=fiyat_val,
                maliyet=maliyet_val,
                min_marj_yuzde=min_marj_val,
            )
            db.add(new_product)

        records_processed += 1

    db.commit()
    return records_processed


if __name__ == "__main__":
    session = SessionLocal()
    try:
        count = load_products_from_excel(session)
        total_in_db = session.query(Product).count()
        print(f"✓ Excel işlendi: {count} satır.")
        print(f"✓ Veritabanındaki güncel toplam ürün: {total_in_db}")
    finally:
        session.close()