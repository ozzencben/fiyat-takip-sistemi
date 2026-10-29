import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ..adapters.books_toscrape import BooksToScrapeAdapter
from ..adapters.fake_store import FakeStoreAdapter
from ..adapters.webscraper_io import WebScraperIOAdapter
from ..core.db import Base, SessionLocal, engine
from ..core.load_excel import load_products_from_excel
from ..core.matching import run_product_matching
from ..core.models import Competitor, PriceSnapshot
from ..core.report import (
    generate_fallback_report,
    prepare_report_data,
    save_last_report,
)
from .generate_sample_excel import create_excel
from .seed_history import seed_price_history

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRICES_JSON_PATH = PROJECT_ROOT / "data" / "prices.json"

# Sahte mağaza (Rakip C) başlangıç fiyatları (bazıları bizden ucuz, bazıları pahalı)
INITIAL_FAKE_STORE_PRODUCTS: List[Dict[str, Any]] = [
    {"id": 1, "name": "A Light in the Attic (Ciltli)", "price": 1932.00, "in_stock": True, "url": "http://localhost:8001/products/1"},
    {"id": 2, "name": "Tipping the Velvet", "price": 2322.00, "in_stock": True, "url": "http://localhost:8001/products/2"},
    {"id": 3, "name": "Soumission", "price": 1840.00, "in_stock": True, "url": "http://localhost:8001/products/3"},
    {"id": 4, "name": "Sharp Objects - Roman", "price": 1764.35, "in_stock": True, "url": "http://localhost:8001/products/4"},
    {"id": 5, "name": "Sapiens: A Brief History", "price": 2024.00, "in_stock": True, "url": "http://localhost:8001/products/5"},
    {"id": 6, "name": "The Requiem Red", "price": 972.00, "in_stock": True, "url": "http://localhost:8001/products/6"},
    {"id": 7, "name": "The Dirty Little Secrets of Getting Your Dream Job", "price": 1242.00, "in_stock": True, "url": "http://localhost:8001/products/7"},
    {"id": 8, "name": "The Coming Woman: A Novel", "price": 810.00, "in_stock": True, "url": "http://localhost:8001/products/8"},
    {"id": 9, "name": "The Boys in the Boat", "price": 874.00, "in_stock": True, "url": "http://localhost:8001/products/9"},
    {"id": 10, "name": "The Black Maria", "price": 1928.36, "in_stock": True, "url": "http://localhost:8001/products/10"},
    {"id": 11, "name": "Starving Hearts (Triangular Trade Trilogy)", "price": 506.00, "in_stock": True, "url": "http://localhost:8001/products/11"},
    {"id": 12, "name": "Shakespeare's Sonnets", "price": 821.71, "in_stock": True, "url": "http://localhost:8001/products/12"},
    {"id": 13, "name": "Set Me Free", "price": 644.00, "in_stock": True, "url": "http://localhost:8001/products/13"},
    {"id": 14, "name": "Scott Pilgrim's Precious Little Life", "price": 2268.00, "in_stock": True, "url": "http://localhost:8001/products/14"},
    {"id": 15, "name": "Rip it Up and Start Again", "price": 1288.00, "in_stock": True, "url": "http://localhost:8001/products/15"},
    {"id": 16, "name": "Our Band Could Be Your Life", "price": 2484.00, "in_stock": True, "url": "http://localhost:8001/products/16"},
    {"id": 17, "name": "Olio Şiir Kitabı", "price": 874.00, "in_stock": True, "url": "http://localhost:8001/products/17"},
    {"id": 18, "name": "Mesaerion: Best Science Hikayeleri 1800-1849", "price": 1460.00, "in_stock": True, "url": "http://localhost:8001/products/18"},
    {"id": 19, "name": "Libertarian for Beginners Rehberi", "price": 1980.00, "in_stock": True, "url": "http://localhost:8001/products/19"},
    {"id": 20, "name": "Only the Himalayas Gezi Kitabı", "price": 1760.00, "in_stock": True, "url": "http://localhost:8001/products/20"},
    {"id": 21, "name": "Foolproof Preserving Reçel Rehberi", "price": 1190.00, "in_stock": True, "url": "http://localhost:8001/products/21"},
    {"id": 22, "name": "In Her Wake (Polisiye)", "price": 525.00, "in_stock": True, "url": "http://localhost:8001/products/22"},
    {"id": 23, "name": "How Music Works", "price": 1440.00, "in_stock": True, "url": "http://localhost:8001/products/23"},
    {"id": 24, "name": "Chase Me (Paris Nights)", "price": 990.00, "in_stock": True, "url": "http://localhost:8001/products/24"},
    {"id": 25, "name": "Black Dust", "price": 1410.00, "in_stock": True, "url": "http://localhost:8001/products/25"},
    {"id": 26, "name": "Lenovo IdeaTab (7 inç Android)", "price": 2490.00, "in_stock": True, "url": "http://localhost:8001/products/26"},
    {"id": 27, "name": "IdeaTab A3500L", "price": 3180.00, "in_stock": True, "url": "http://localhost:8001/products/27"},
    {"id": 28, "name": "Acer Iconia (16GB Tablet)", "price": 3420.00, "in_stock": True, "url": "http://localhost:8001/products/28"},
    {"id": 29, "name": "Iconia B1-730HD", "price": 3520.00, "in_stock": False, "url": "http://localhost:8001/products/29"},
    {"id": 30, "name": "Memo Pad HD 7", "price": 3690.00, "in_stock": True, "url": "http://localhost:8001/products/30"},
    {"id": 31, "name": "Asus MeMO Pad", "price": 3490.00, "in_stock": True, "url": "http://localhost:8001/products/31"},
    {"id": 32, "name": "Amazon Kindle", "price": 3680.00, "in_stock": True, "url": "http://localhost:8001/products/32"},
    {"id": 33, "name": "IdeaTab A8-50", "price": 4310.00, "in_stock": True, "url": "http://localhost:8001/products/33"},
    {"id": 34, "name": "iPad Mini Retina (Wi-Fi)", "price": 18950.00, "in_stock": True, "url": "http://localhost:8001/products/34"},
    {"id": 35, "name": "Apple iPad Air", "price": 21250.00, "in_stock": True, "url": "http://localhost:8001/products/35"},
]

# Rakip A (BooksToScrape) başlangıç referans fiyatları (1 £ = 40 TL)
BASELINE_RAKIP_A_SNAPSHOTS: List[Dict[str, Any]] = [
    {"name": "A Light in the Attic", "price": 2070.80, "url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"},
    {"name": "Tipping the Velvet", "price": 2149.60, "url": "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html"},
    {"name": "Soumission", "price": 2004.00, "url": "https://books.toscrape.com/catalogue/soumission_998/index.html"},
    {"name": "Sharp Objects", "price": 1912.80, "url": "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"},
    {"name": "Sapiens: A Brief History of Humankind", "price": 2169.20, "url": "https://books.toscrape.com/catalogue/sapiens-a-brief-history-of-humankind_996/index.html"},
    {"name": "The Requiem Red", "price": 906.00, "url": "https://books.toscrape.com/catalogue/the-requiem-red_995/index.html"},
    {"name": "The Dirty Little Secrets of Getting Your Dream Job", "price": 1333.60, "url": "https://books.toscrape.com/catalogue/the-dirty-little-secrets-of-getting-your-dream-job_994/index.html"},
    {"name": "The Coming Woman: A Novel Based on the Life of the Infamous Feminist, Victoria Woodhull", "price": 717.20, "url": "https://books.toscrape.com/catalogue/the-coming-woman_993/index.html"},
    {"name": "The Boys in the Boat: Nine Americans and Their Epic Quest for Gold at the 1936 Berlin Olympics", "price": 904.00, "url": "https://books.toscrape.com/catalogue/the-boys-in-the-boat_992/index.html"},
    {"name": "The Black Maria", "price": 2086.00, "url": "https://books.toscrape.com/catalogue/the-black-maria_991/index.html"},
    {"name": "Starving Hearts (Triangular Trade Trilogy, #1)", "price": 559.60, "url": "https://books.toscrape.com/catalogue/starving-hearts_990/index.html"},
    {"name": "Shakespeare's Sonnets", "price": 826.40, "url": "https://books.toscrape.com/catalogue/shakespeares-sonnets_989/index.html"},
    {"name": "Set Me Free", "price": 698.40, "url": "https://books.toscrape.com/catalogue/set-me-free_988/index.html"},
    {"name": "Scott Pilgrim's Precious Little Life (Scott Pilgrim #1)", "price": 2091.60, "url": "https://books.toscrape.com/catalogue/scott-pilgrims-precious-little-life_987/index.html"},
    {"name": "Rip it Up and Start Again", "price": 1400.80, "url": "https://books.toscrape.com/catalogue/rip-it-up-and-start-again_986/index.html"},
    {"name": "Our Band Could Be Your Life: Scenes from the American Indie Underground, 1981-1991", "price": 2290.00, "url": "https://books.toscrape.com/catalogue/our-band-could-be-your-life_985/index.html"},
    {"name": "Olio", "price": 955.20, "url": "https://books.toscrape.com/catalogue/olio_984/index.html"},
    {"name": "Mesaerion: The Best Science Fiction Stories 1800-1849", "price": 1503.60, "url": "https://books.toscrape.com/catalogue/mesaerion-the-best-science-fiction-stories-1800-1849_983/index.html"},
    {"name": "Libertarianism for Beginners", "price": 2053.20, "url": "https://books.toscrape.com/catalogue/libertarianism-for-beginners_982/index.html"},
    {"name": "It's Only the Himalayas", "price": 1806.80, "url": "https://books.toscrape.com/catalogue/its-only-the-himalayas_981/index.html"},
    {"name": "In Her Wake", "price": 513.60, "url": "https://books.toscrape.com/catalogue/in-her-wake_980/index.html"},
    {"name": "How Music Works", "price": 1492.80, "url": "https://books.toscrape.com/catalogue/how-music-works_979/index.html"},
    {"name": "Foolproof Preserving: A Guide to Small Batch Jams, Jellies, Pickles, Condiments, and More: A Foolproof Guide to Making Small Batch Jams, Jellies, Pickles, Condiments, and More", "price": 1220.80, "url": "https://books.toscrape.com/catalogue/foolproof-preserving_978/index.html"},
    {"name": "Chase Me (Paris Nights #2)", "price": 1010.80, "url": "https://books.toscrape.com/catalogue/chase-me-paris-nights-2_977/index.html"},
    {"name": "Black Dust", "price": 1381.20, "url": "https://books.toscrape.com/catalogue/black-dust_976/index.html"},
]

# Rakip B (WebScraper.io) başlangıç referans fiyatları (1 $ = 35 TL)
BASELINE_RAKIP_B_SNAPSHOTS: List[Dict[str, Any]] = [
    {"name": "Lenovo IdeaTab", "price": 2449.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/10"},
    {"name": "IdeaTab A3500L", "price": 3114.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/15"},
    {"name": "Acer Iconia", "price": 3394.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/11"},
    {"name": "Iconia B1-730HD", "price": 3499.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/27"},
    {"name": "Memo Pad HD 7", "price": 3569.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/23"},
    {"name": "Asus MeMO Pad", "price": 3604.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/12"},
    {"name": "Amazon Kindle", "price": 3639.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/13"},
    {"name": "IdeaTab A8-50", "price": 4269.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/28"},
    {"name": "MeMO Pad 7", "price": 4584.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/20"},
    {"name": "iPad Mini Retina", "price": 18829.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/14"},
    {"name": "Apple iPad Air", "price": 21139.65, "url": "https://webscraper.io/test-sites/e-commerce/allinone/product/30"},
]


def reset_demo_state() -> None:
    """
    Kılavuz Gün 3 (19:30-22:00 Cila ve demo modu):
    - Veritabanını temiz başlangıç durumuna getirir
    - Sahte mağaza fiyatlarını (data/prices.json) başlangıç değerlerine döndürür
    - Excel ürünlerini, başlangıç rakip fiyatlarını ve eşleşmeleri yükler
    - 14 günlük örnek fiyat geçmişini (seed_history) oluşturur
    """
    print("=" * 80)
    print("🔄 [DEMO SIFIRLAMA] Sistem temiz başlangıç durumuna getiriliyor...")
    print("=" * 80)

    # 1. Sahte mağaza fiyatlarını (data/prices.json) başlangıç değerlerine döndür
    PRICES_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PRICES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(INITIAL_FAKE_STORE_PRODUCTS, f, ensure_ascii=False, indent=2)
    print(f"✓ Sahte mağaza fiyatları ({len(INITIAL_FAKE_STORE_PRODUCTS)} ürün) başlangıç değerlerine döndürüldü.")

    # 2. Excel dosyasını doğrula / oluştur
    create_excel()

    # 3. Veritabanı tablolarını sıfırla ve yeniden oluştur
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("✓ Veritabanı tabloları temizlendi ve yeniden oluşturuldu.")

    session = SessionLocal()
    try:
        # 4. Ürünleri Excel'den yükle
        prod_count = load_products_from_excel(session)
        print(f"✓ Excel'den {prod_count} ürün veritabanına yüklendi.")

        # 5. Rakipleri ve başlangıç snapshot kayıtlarını ekle
        comp_a = Competitor(
            ad=BooksToScrapeAdapter.COMPETITOR_NAME,
            base_url=BooksToScrapeAdapter.BASE_URL,
        )
        comp_c = Competitor(
            ad=FakeStoreAdapter.COMPETITOR_NAME,
            base_url=FakeStoreAdapter.BASE_URL,
        )
        comp_b = Competitor(
            ad=WebScraperIOAdapter.COMPETITOR_NAME,
            base_url=WebScraperIOAdapter.BASE_URL,
        )
        session.add_all([comp_a, comp_c, comp_b])
        session.commit()
        session.refresh(comp_a)
        session.refresh(comp_c)
        session.refresh(comp_b)

        now = datetime.utcnow()
        for item in BASELINE_RAKIP_A_SNAPSHOTS:
            session.add(
                PriceSnapshot(
                    competitor_id=comp_a.id,
                    ham_urun_adi=item["name"],
                    url=item["url"],
                    fiyat=item["price"],
                    stokta=True,
                    cekilme_zamani=now,
                )
            )
        for item in INITIAL_FAKE_STORE_PRODUCTS:
            session.add(
                PriceSnapshot(
                    competitor_id=comp_c.id,
                    ham_urun_adi=item["name"],
                    url=item["url"],
                    fiyat=item["price"],
                    stokta=bool(item.get("in_stock", True)),
                    cekilme_zamani=now,
                )
            )
        for item in BASELINE_RAKIP_B_SNAPSHOTS:
            session.add(
                PriceSnapshot(
                    competitor_id=comp_b.id,
                    ham_urun_adi=item["name"],
                    url=item["url"],
                    fiyat=item["price"],
                    stokta=True,
                    cekilme_zamani=now,
                )
            )
        session.commit()
        print("✓ Başlangıç rakip fiyat kayıtları (Rakip A, Rakip B, Rakip C) yüklendi.")

        # 6. Eşleştirmeleri çalıştır (66 otomatik_onayli + 4 onay_bekliyor)
        run_product_matching(session)

        # 7. Son 14 günlük örnek geçmiş verisini yükle
        seed_price_history(session, days=14)

        # 8. Başlangıç özet raporunu oluştur ve kaydet
        report_data = prepare_report_data(session)
        baseline_llm_report = (
            f"{report_data.get('rapor_tarihi', '')[:10]} tarihli fiyat takip verilerine göre, toplam "
            f"{report_data.get('toplam_urun_sayisi', 35)} ürünlük portföyümüzde rekabetçi konumumuz yakından izlenmektedir. "
            f"Rakiplerimiz, takip edilen {report_data.get('toplam_urun_sayisi', 35)} ürünün "
            f"{report_data.get('rakibin_ucuz_oldugu_urun_sayisi', 32)} tanesinde bizden daha uygun fiyatlar sunarken "
            f"{report_data.get('avantajli_urun_sayisi', 3)} üründe fiyat avantajı tarafımızdadır. "
            "Özellikle \"A Light in the Attic (Ciltli)\", \"Soumission\" ve \"Sapiens: A Brief History\" gibi kritik ürünlerde "
            "Rakip C (Sahte Mağaza) fiyatlarının gerisinde kaldığımız gözlemlenmiştir. "
            "Kar marjlarımızı koruyarak rekabetçi seviyelere dönmek için önerilen fiyat revizyonlarının uygulanması önem taşımaktadır.\n\n"
            "Aksiyon Önerileri:\n"
            "1. \"A Light in the Attic (Ciltli)\" (Önerilen: 1912.68 TL), \"Soumission\" (Önerilen: 1821.60 TL) ve \"Sapiens\" (Önerilen: 2003.76 TL) "
            "ürünlerinde minimum kâr marjını koruyan %1 altı fiyatlandırma stratejisine geçiş yapın.\n"
            "2. Rakipte stoğu tükenen \"Iconia B1-730HD\" ürününde fiyat kırmak yerine mevcut satış fiyatınızı ve kâr marjınızı koruyun."
        )
        save_last_report(baseline_llm_report, report_data)
        print("✓ Başlangıç yönetici özeti (data/last_report.json) hazırlandı.")

        print("\n" + "=" * 80)
        print("✅ [DEMO HAZIR] Sistem video çekimi ve canlı sunum için başlangıç durumunda!")
        print("=" * 80)
    finally:
        session.close()


if __name__ == "__main__":
    reset_demo_state()

