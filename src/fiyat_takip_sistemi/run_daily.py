import sys
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import desc
from sqlalchemy.orm import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .core.db import SessionLocal
from .core.matching import run_product_matching
from .core.models import Competitor, Match, PriceSnapshot, Product
from .adapters.books_toscrape import BooksToScrapeAdapter, save_snapshots_to_db as save_books_snapshots
from .adapters.fake_store import FakeStoreAdapter, save_snapshots_to_db as save_fake_store_snapshots


def run_scrapers(db: Session) -> None:
    """
    Kılavuz gereksinimi Adım 1: Adaptörleri çalıştır ve ham fiyatları veritabanına kaydet.
    """
    print("\n" + "=" * 80)
    print("🚀 [ADIM 1] Rakip Site Adaptörleri Çalıştırılıyor...")
    print("=" * 80)

    # 1. Rakip A (BooksToScrape)
    try:
        books_adapter = BooksToScrapeAdapter()
        print("\n▶ Rakip A (BooksToScrape) fiyatları çekiliyor...")
        books_data = books_adapter.fetch_products(max_pages=5)
        saved_a = save_books_snapshots(db, books_data)
        print(f"✓ Rakip A: {saved_a} snapshot kaydedildi.")
        books_adapter.close()
    except Exception as e:
        print(f"⚠️ Rakip A çekilirken hata oluştu: {e}")

    # 2. Rakip C (Sahte Mağaza)
    try:
        fake_adapter = FakeStoreAdapter()
        print("\n▶ Rakip C (Sahte Mağaza) fiyatları çekiliyor...")
        fake_data = fake_adapter.fetch_products()
        saved_c = save_fake_store_snapshots(db, fake_data)
        print(f"✓ Rakip C: {saved_c} snapshot kaydedildi.")
        fake_adapter.close()
    except Exception as e:
        print(
            f"⚠️ Rakip C çekilemedi (Sahte mağaza sunucusu port 8001 açık mı?): {e}\n"
            f"   (Not: Önceden kaydedilmiş snapshot verileri kullanılacak.)"
        )


def build_comparison_dataframe(db: Session) -> pd.DataFrame:
    """
    Kılavuz gereksinimi Adım 3 & 4:
    Her onaylı eşleşme için en son fiyatı al ve karşılaştırma tablosunu oluştur.
    Sütunlar: Ürün, Benim fiyatım, Rakip A, Rakip C, Fark, Uyarı
    """
    products = db.query(Product).order_by(Product.id.asc()).all()
    competitors = {c.id: c.ad for c in db.query(Competitor).all()}

    # Rakip ID'lerini belirle
    rakip_a_id = next((cid for cid, name in competitors.items() if "BooksToScrape" in name or "Rakip A" in name), 1)
    rakip_c_id = next((cid for cid, name in competitors.items() if "Sahte Magaza" in name or "Rakip C" in name), 2)

    rows: List[Dict[str, Any]] = []

    for product in products:
        benim_fiyat = product.fiyat

        # Ürünün onaylı eşleşmelerini getir (otomatik_onayli veya onayli)
        matches = (
            db.query(Match)
            .filter(
                Match.product_id == product.id,
                Match.durum.in_(["otomatik_onayli", "onayli"]),
            )
            .all()
        )

        fiyat_rakip_a: Optional[float] = None
        fiyat_rakip_c: Optional[float] = None

        for match in matches:
            # İlgili rakibin bu ürün için kaydettiği en son snapshot fiyatını bul
            latest_snapshot = (
                db.query(PriceSnapshot)
                .filter(
                    PriceSnapshot.competitor_id == match.competitor_id,
                    PriceSnapshot.ham_urun_adi == match.ham_urun_adi,
                )
                .order_by(desc(PriceSnapshot.id))
                .first()
            )

            if latest_snapshot:
                if match.competitor_id == rakip_a_id:
                    fiyat_rakip_a = latest_snapshot.fiyat
                elif match.competitor_id == rakip_c_id:
                    fiyat_rakip_c = latest_snapshot.fiyat

        # Rakipler arasındaki en ucuz fiyatı tespit et
        valid_competitor_prices = [p for p in (fiyat_rakip_a, fiyat_rakip_c) if p is not None]

        if valid_competitor_prices:
            min_rakip_fiyat = min(valid_competitor_prices)
            fark = round(min_rakip_fiyat - benim_fiyat, 2)
            fark_str = f"{fark:+.2f} TL"

            # Kılavuz kuralı: "Rakip senden ucuzsa uyarı sütununa 'RAKİP UCUZ' yaz."
            if min_rakip_fiyat < benim_fiyat:
                uyari = "RAKİP UCUZ"
            else:
                uyari = "-"
        else:
            fark_str = "-"
            uyari = "-"

        rows.append({
            "Ürün": product.urun_adi,
            "Benim fiyatım": f"{benim_fiyat:.2f} TL",
            "Rakip A": f"{fiyat_rakip_a:.2f} TL" if fiyat_rakip_a is not None else "-",
            "Rakip C": f"{fiyat_rakip_c:.2f} TL" if fiyat_rakip_c is not None else "-",
            "Fark": fark_str,
            "Uyarı": uyari,
        })

    df = pd.DataFrame(rows)
    return df


def main() -> None:
    """
    Günlük akışı uçtan uca çalıştıran ana fonksiyon.
    1. Adaptörleri çalıştırır
    2. Eşleştirmeyi günceller
    3. Fiyat karşılaştırma tablosunu terminale basar
    """
    session = SessionLocal()
    try:
        # 1. Adaptörleri çalıştır
        run_scrapers(session)

        # 2. Yeni ürünleri eşleştir
        print("\n" + "=" * 80)
        print("🔗 [ADIM 2] Ürün Eşleştirme Motoru Çalıştırılıyor...")
        print("=" * 80)
        run_product_matching(session)

        # 3. Karşılaştırma tablosunu oluştur ve terminale bas
        print("\n" + "=" * 80)
        print("📊 [ADIM 3] GÜNLÜK FİYAT KARŞILAŞTIRMA VE REKABET TABLOSU")
        print("=" * 80)

        df = build_comparison_dataframe(session)

        # Terminalde sütunların kırpılmaması için pandas ayarları
        pd.set_option("display.max_columns", None)
        pd.set_option("display.max_rows", None)
        pd.set_option("display.width", 1000)
        pd.set_option("display.colheader_justify", "left")

        # Tabloyu yazdır
        print(df.to_string(index=False))

        # Özet istatistikler
        toplam_urun = len(df)
        rakip_ucuz_sayisi = (df["Uyarı"] == "RAKİP UCUZ").sum()
        print("\n" + "-" * 80)
        print(f"📈 [GÜN SONU ÖZETİ]")
        print(f"  • İncelenen Ürün Sayısı        : {toplam_urun}")
        print(f"  • Rakiplerin Daha Ucuz Olduğu : {rakip_ucuz_sayisi} ürün (Uyarı: RAKİP UCUZ)")
        print(f"  • Bizim Daha Avantajlı Olduğumuz: {toplam_urun - rakip_ucuz_sayisi} ürün")
        print("-" * 80 + "\n")

    finally:
        session.close()


if __name__ == "__main__":
    main()