import sys
import time
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ..core.db import SessionLocal
from ..core.models import Competitor, PriceSnapshot
from .base import BaseAdapter

# Kılavuz gereksinimi: Demo için sabit kur çarpanı (1 £ = 40 TL)
KUR_GBP_TL: float = 40.0


class BooksToScrapeAdapter(BaseAdapter):
    """
    books.toscrape.com sitesinden ürünleri nazikçe ve güvenli şekilde çeken adaptör.
    """

    COMPETITOR_NAME = "Rakip A (BooksToScrape)"
    BASE_URL = "https://books.toscrape.com"
    CATALOGUE_URL_TEMPLATE = "https://books.toscrape.com/catalogue/page-{page}.html"

    def __init__(self, exchange_rate: float = KUR_GBP_TL, request_delay: float = 1.0):
        super().__init__(competitor_name=self.COMPETITOR_NAME, base_url=self.BASE_URL)
        self.exchange_rate = exchange_rate
        self.request_delay = request_delay
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FiyatTakipBot/1.0"
            },
            timeout=15.0,
            follow_redirects=True,
        )

    def check_robots_txt(self) -> None:
        """Kılavuz gereksinimi: Kazımaya başlamadan önce robots.txt dosyasını kontrol eder."""
        robots_url = urljoin(self.base_url, "/robots.txt")
        try:
            resp = self.client.get(robots_url)
            print(f"[Robots.txt] Durum Kodu: {resp.status_code}")
        except Exception as e:
            print(f"[Robots.txt] Kontrol edilirken uyarı: {e}")

    def _clean_price(self, raw_price: str) -> float:
        """
        Fiyat metnindeki para birimi işaretlerini (£, Â vb.) temizler ve float döndürür.
        """
        cleaned = raw_price.replace("£", "").replace("Â", "").replace(",", ".").strip()
        return float(cleaned)

    def _fetch_page_with_retry(self, url: str, max_retries: int = 3) -> str | None:
        """
        Hata durumunda 2-3 kez yeniden deneyen güvenli HTTP GET isteği.
        """
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.client.get(url)
                if resp.status_code == 200:
                    # UTF-8 karakter kodlaması güvencesi
                    return resp.content.decode("utf-8", errors="replace")
                print(f"Uyarı: {url} -> HTTP {resp.status_code} (Deneme {attempt}/{max_retries})")
            except Exception as e:
                print(f"Hata: {url} çekilemedi: {e} (Deneme {attempt}/{max_retries})")

            if attempt < max_retries:
                time.sleep(self.request_delay * attempt)
        return None

    def fetch_products(self, max_pages: int = 5) -> List[Dict[str, Any]]:
        """
        Belirtilen sayfa adedi kadar dolaşarak ürünleri toplar.
        Kılavuz gereksinimi: En az 1 saniye bekleme, name, price (TL), in_stock, url döndürme.
        """
        self.check_robots_txt()
        products: List[Dict[str, Any]] = []

        print(f"🚀 {self.competitor_name} üzerinden veri çekimi başlıyor (Hedef: {max_pages} sayfa)...")

        for page in range(1, max_pages + 1):
            page_url = self.CATALOGUE_URL_TEMPLATE.format(page=page)
            print(f"📄 Sayfa {page}/{max_pages} çekiliyor: {page_url}")

            html_content = self._fetch_page_with_retry(page_url)
            if not html_content:
                print(f"⚠️ Sayfa {page} alınamadı, sonraki sayfaya geçiliyor.")
                continue

            soup = BeautifulSoup(html_content, "html.parser")
            pods = soup.select("article.product_pod")

            for pod in pods:
                # Başlık: h3 a etiketinin title attribute'u tam adı verir
                title_elem = pod.select_one("h3 a")
                name = title_elem["title"].strip() if title_elem and "title" in title_elem.attrs else "Bilinmeyen Kitap"

                # URL: relative bağlantıyı tam URL'ye çevir
                href = title_elem["href"].strip() if title_elem and "href" in title_elem.attrs else ""
                full_url = urljoin(page_url, href)

                # Fiyat: p.price_color içindedir
                price_elem = pod.select_one("p.price_color")
                raw_price_str = price_elem.text.strip() if price_elem else "0"
                gbp_price = self._clean_price(raw_price_str)
                tl_price = round(gbp_price * self.exchange_rate, 2)

                # Stok Durumu: p.instock.availability içindeki metin
                stock_elem = pod.select_one("p.instock.availability")
                in_stock = ("in stock" in stock_elem.text.lower()) if stock_elem else True

                products.append({
                    "name": name,
                    "price": tl_price,
                    "raw_gbp_price": gbp_price,
                    "in_stock": in_stock,
                    "url": full_url,
                })

            # Kılavuz gereksinimi: İstekler arasında en az 1 saniye bekle
            if page < max_pages:
                time.sleep(self.request_delay)

        print(f"✓ Toplam {len(products)} ürün başarıyla çekildi.")
        return products

    def close(self):
        self.client.close()


def save_snapshots_to_db(db: Session, scraped_products: List[Dict[str, Any]]) -> int:
    """
    Çekilen ürünleri price_snapshots tablosuna kaydeder.
    """
    competitor = db.query(Competitor).filter(Competitor.ad == BooksToScrapeAdapter.COMPETITOR_NAME).first()
    if not competitor:
        competitor = Competitor(
            ad=BooksToScrapeAdapter.COMPETITOR_NAME,
            base_url=BooksToScrapeAdapter.BASE_URL,
        )
        db.add(competitor)
        db.commit()
        db.refresh(competitor)

    now = datetime.utcnow()
    snapshots = [
        PriceSnapshot(
            competitor_id=competitor.id,
            ham_urun_adi=item["name"],
            url=item["url"],
            fiyat=item["price"],
            stokta=item["in_stock"],
            cekilme_zamani=now,
        )
        for item in scraped_products
    ]

    db.add_all(snapshots)
    db.commit()
    return len(snapshots)


if __name__ == "__main__":
    adapter = BooksToScrapeAdapter()
    try:
        scraped = adapter.fetch_products(max_pages=5)
        
        session = SessionLocal()
        try:
            saved_count = save_snapshots_to_db(session, scraped)
            total_snapshots = session.query(PriceSnapshot).count()
            print(f"✓ price_snapshots tablosuna {saved_count} yeni kayıt yazıldı.")
            print(f"✓ Tablodaki toplam snapshot sayısı: {total_snapshots}")

            # Örnek ilk 3 kaydı göster
            print("\nÖrnek Fiyat Kayıtları (İlk 3 Ürün):")
            sample = (
                session.query(PriceSnapshot)
                .order_by(PriceSnapshot.id.desc())
                .limit(3)
                .all()
            )
            for s in reversed(sample):
                print(f"  • {s.ham_urun_adi} -> {s.fiyat} TL | Stokta: {s.stokta} | URL: {s.url}")
        finally:
            session.close()
    finally:
        adapter.close()
