import sys
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import desc
from sqlalchemy.orm import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .core.db import SessionLocal
from .core.logger import get_logger
from .core.matching import run_product_matching
from .core.models import Competitor, Match, PriceSnapshot, Product
from .core.rules import evaluate_rules, print_alerts_summary
from .core.report import run_daily_report, prepare_report_data
from .core.notify import format_daily_notification_message, send_telegram_message
from .adapters.books_toscrape import BooksToScrapeAdapter, save_snapshots_to_db as save_books_snapshots
from .adapters.webscraper_io import WebScraperIOAdapter, save_snapshots_to_db as save_webscraper_snapshots
from .adapters.fake_store import FakeStoreAdapter, save_snapshots_to_db as save_fake_store_snapshots

logger = get_logger("run_daily")


def run_scrapers(db: Session) -> None:
    """
    Kılavuz gereksinimi Adım 1 & Gün 2 (17:00-22:00):
    Adaptörleri (Rakip A, Rakip B, Rakip C) çalıştır ve ham fiyatları veritabanına kaydet.
    Bir adaptör hata verirse akış durmasın; hata kaydedilsin ve Telegram'a
    'Rakip X adaptörü çalışmadı' mesajı gitsin.
    """
    print("\n" + "=" * 80)
    print("🚀 [ADIM 1] Rakip Site Adaptörleri Çalıştırılıyor...")
    print("=" * 80)
    logger.info("Adım 1: Rakip site adaptörleri çalıştırılıyor.")

    # 1. Rakip A (BooksToScrape)
    books_adapter = BooksToScrapeAdapter()
    try:
        print("\n▶ Rakip A (BooksToScrape) fiyatları çekiliyor...")
        logger.info("Rakip A (BooksToScrape) veri çekimi başladı.")
        books_data = books_adapter.fetch_products(max_pages=5)
        saved_a = save_books_snapshots(db, books_data)
        print(f"✓ Rakip A: {saved_a} yeni snapshot kaydedildi.")
        logger.info(f"Rakip A (BooksToScrape) tamamlandı: {saved_a} yeni snapshot kaydedildi.")
    except Exception as e:
        error_msg = f"Rakip A adaptörü çalışmadı ({e})"
        print(f"⚠️ {error_msg}")
        logger.error(error_msg)
        send_telegram_message(f"⚠️ <b>Sistem Uyarısı:</b> Rakip A adaptörü çalışmadı.\nDetay: {e}")
    finally:
        books_adapter.close()

    # 2. Rakip B (WebScraper.io - Elektronik Test Sitesi)
    webscraper_adapter = WebScraperIOAdapter()
    try:
        print("\n▶ Rakip B (WebScraper.io) fiyatları çekiliyor...")
        logger.info("Rakip B (WebScraper.io) veri çekimi başladı.")
        webscraper_data = webscraper_adapter.fetch_products()
        saved_b = save_webscraper_snapshots(db, webscraper_data)
        print(f"✓ Rakip B: {saved_b} yeni snapshot kaydedildi.")
        logger.info(f"Rakip B (WebScraper.io) tamamlandı: {saved_b} yeni snapshot kaydedildi.")
    except Exception as e:
        error_msg = f"Rakip B adaptörü çalışmadı ({e})"
        print(f"⚠️ {error_msg}")
        logger.error(error_msg)
        send_telegram_message(f"⚠️ <b>Sistem Uyarısı:</b> Rakip B adaptörü çalışmadı.\nDetay: {e}")
    finally:
        webscraper_adapter.close()

    # 3. Rakip C (Sahte Mağaza)
    fake_adapter = FakeStoreAdapter()
    try:
        print("\n▶ Rakip C (Sahte Mağaza) fiyatları çekiliyor...")
        logger.info("Rakip C (Sahte Mağaza) veri çekimi başladı.")
        fake_data = fake_adapter.fetch_products()
        saved_c = save_fake_store_snapshots(db, fake_data)
        print(f"✓ Rakip C: {saved_c} yeni snapshot kaydedildi.")
        logger.info(f"Rakip C (Sahte Mağaza) tamamlandı: {saved_c} yeni snapshot kaydedildi.")
    except Exception as e:
        error_msg = f"Rakip C adaptörü çalışmadı ({e})"
        print(
            f"⚠️ {error_msg}\n"
            f"   (Not: Önceden kaydedilmiş snapshot verileri kullanılacak.)"
        )
        logger.error(error_msg)
        send_telegram_message(f"⚠️ <b>Sistem Uyarısı:</b> Rakip C adaptörü çalışmadı.\nDetay: {e}")
    finally:
        fake_adapter.close()


def build_comparison_dataframe(db: Session) -> pd.DataFrame:
    """
    Kılavuz gereksinimi Adım 3 & 4:
    Her onaylı eşleşme için en son fiyatı al ve karşılaştırma tablosunu oluştur.
    Sütunlar: Ürün, Benim fiyatım, Rakip A, Rakip B, Rakip C, Fark, Uyarı
    """
    products = db.query(Product).order_by(Product.id.asc()).all()
    competitors = {c.id: c.ad for c in db.query(Competitor).all()}

    # Rakip ID'lerini belirle
    rakip_a_id = next((cid for cid, name in competitors.items() if "BooksToScrape" in name or "Rakip A" in name), 1)
    rakip_b_id = next((cid for cid, name in competitors.items() if "WebScraper" in name or "Rakip B" in name), 3)
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
        fiyat_rakip_b: Optional[float] = None
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
                elif match.competitor_id == rakip_b_id:
                    fiyat_rakip_b = latest_snapshot.fiyat
                elif match.competitor_id == rakip_c_id:
                    fiyat_rakip_c = latest_snapshot.fiyat

        # Rakipler arasındaki en ucuz fiyatı tespit et
        valid_competitor_prices = [
            p for p in (fiyat_rakip_a, fiyat_rakip_b, fiyat_rakip_c) if p is not None
        ]

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
            "Rakip B": f"{fiyat_rakip_b:.2f} TL" if fiyat_rakip_b is not None else "-",
            "Rakip C": f"{fiyat_rakip_c:.2f} TL" if fiyat_rakip_c is not None else "-",
            "Fark": fark_str,
            "Uyarı": uyari,
        })

    df = pd.DataFrame(rows)
    return df


def run_daily() -> None:
    """
    Günlük akışı uçtan uca çalıştıran ana fonksiyon.
    1. Adaptörleri çalıştırır
    2. Eşleştirmeyi günceller
    3. Fiyat karşılaştırma tablosunu terminale basar
    4. Kural motorunu değerlendirir
    5. LLM günlük raporunu üretir
    6. Telegram sabah bildirimini gönderir
    """
    logger.info("=== GÜNLÜK FİYAT TAKİP AKIŞI (run_daily) BAŞLADI ===")
    session = SessionLocal()
    try:
        # 1. Adaptörleri çalıştır
        run_scrapers(session)

        # 2. Yeni ürünleri eşleştir
        print("\n" + "=" * 80)
        print("🔗 [ADIM 2] Ürün Eşleştirme Motoru Çalıştırılıyor...")
        print("=" * 80)
        logger.info("Adım 2: Ürün eşleştirme motoru çalıştırılıyor.")
        match_stats = run_product_matching(session)
        logger.info(
            f"Adım 2 tamamlandı: Otomatik onaylı={match_stats['otomatik_onayli']}, "
            f"Onay bekliyor={match_stats['onay_bekliyor']}, Eşleşme yok={match_stats['eslesme_yok']}"
        )

        # 3. Karşılaştırma tablosunu oluştur ve terminale bas
        print("\n" + "=" * 80)
        print("📊 [ADIM 3] GÜNLÜK FİYAT KARŞILAŞTIRMA VE REKABET TABLOSU")
        print("=" * 80)
        logger.info("Adım 3: Günlük fiyat karşılaştırma tablosu oluşturuluyor.")

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
        rakip_ucuz_sayisi = int((df["Uyarı"] == "RAKİP UCUZ").sum())
        print("\n" + "-" * 80)
        print(f"📈 [GÜN SONU ÖZETİ]")
        print(f"  • İncelenen Ürün Sayısı        : {toplam_urun}")
        print(f"  • Rakibin Ucuz Olduğu Ürünler  : {rakip_ucuz_sayisi}")
        print(f"  • Bizim Avantajlı Olduğumuz    : {toplam_urun - rakip_ucuz_sayisi}")
        print("-" * 80)
        logger.info(
            f"Adım 3 tamamlandı: İncelenen={toplam_urun}, Rakip Ucuz={rakip_ucuz_sayisi}"
        )

        # 4. Kural Motorunu Çalıştır ve Uyarıları Bas (Kılavuz Gün 2)
        print("\n" + "=" * 80)
        print("🧠 [ADIM 4] KURAL MOTORU DEĞERLENDİRMESİ VE AKSIYONLAR")
        print("=" * 80)
        logger.info("Adım 4: Kural motoru çalıştırılıyor.")
        alerts = evaluate_rules(session)
        print_alerts_summary(alerts)
        logger.info(f"Adım 4 tamamlandı: Toplam {len(alerts)} uyarı üretildi.")

        # 5. LLM Günlük Yönetici Raporunu Üret (Kılavuz Gün 2)
        logger.info("Adım 5: LLM günlük yönetici raporu üretiliyor.")
        llm_report = run_daily_report(session)
        logger.info("Adım 5 tamamlandı: Günlük yönetici raporu hazırlandı.")

        # 6. Telegram Bildirimini Gönder (Kılavuz Gün 2)
        print("\n" + "=" * 80)
        print("📲 [ADIM 6] TELEGRAM SABAH BİLDİRİMİ GÖNDERİLİYOR...")
        print("=" * 80)
        logger.info("Adım 6: Telegram sabah bildirimi gönderiliyor.")
        report_data = prepare_report_data(session)
        critical_alerts = report_data.get("en_kritik_uyarilar", [])
        telegram_msg = format_daily_notification_message(llm_report, critical_alerts)
        sent = send_telegram_message(telegram_msg)
        if sent:
            logger.info("Adım 6 tamamlandı: Telegram sabah bildirimi başarıyla gönderildi.")
        else:
            logger.warning("Adım 6 uyarısı: Telegram sabah bildirimi gönderilemedi.")

        logger.info("=== GÜNLÜK FİYAT TAKİP AKIŞI (run_daily) BAŞARIYLA TAMAMLANDI ===")

    except Exception as e:
        logger.exception(f"run_daily akışında beklenmeyen kritik hata: {e}")
        raise
    finally:
        session.close()


def main() -> None:
    run_daily()


if __name__ == "__main__":
    main()