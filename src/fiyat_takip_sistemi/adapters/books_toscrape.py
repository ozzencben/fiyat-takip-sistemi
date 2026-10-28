import sys
import time
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ..core.db import SessionLocal
from ..core.logger import get_logger
from ..core.models import PriceSnapshot
from .base import (
    BaseAdapter,
    parse_and_validate_price,
    save_validated_snapshots_to_db,
)

logger = get_logger("books_toscrape")

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
            logger.warning(f"[Robots.txt] Kontrol edilirken uyarı: {e}")

    def _fetch_page_with_retry(self, url: str, max_retries: int = 3) -> str | None:
        """
        Hata durumunda 2-3 kez yeniden deneyen güvenli HTTP GET isteği.
        """
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.client.get(url)
                if resp.status_code == 200:
                    return resp.content.decode("utf-8", errors="replace")
                logger.warning(
                    f"Sayfa hatası: {url} -> HTTP {resp.status_code} (Deneme {attempt}/{max_retries})"
                )
            except Exception as e:
                logger.warning(
                    f"Bağlantı hatası: {url} çekilemedi: {e} (Deneme {attempt}/{max_retries})"
                )

            if attempt < max_retries:
                time.sleep(self.request_delay * attempt)
        return None

    def fetch_products(self, max_pages: int = 5) -> List[Dict[str, Any]]:
        """
        Belirtilen sayfa adedi kadar dolaşarak ürünleri toplar.
        Sayfa açılmazsa, fiyat bulunamazsa veya 0/negatif çıkarsa kaydı atlar ve loglar.
        """
        self.check_robots_txt()
        products: List[Dict[str, Any]] = []

        print(f"🚀 {self.competitor_name} üzerinden veri çekimi başlıyor (Hedef: {max_pages} sayfa)...")

        for page in range(1, max_pages + 1):
            page_url = self.CATALOGUE_URL_TEMPLATE.format(page=page)
            print(f"📄 Sayfa {page}/{max_pages} çekiliyor: {page_url}")

            html_content = self._fetch_page_with_retry(page_url)
            if not html_content:
                logger.warning(f"[{self.competitor_name}] Sayfa {page} açılamadığı için atlandı: {page_url}")
                continue

            soup = BeautifulSoup(html_content, "html.parser")
            pods = soup.select("article.product_pod")

            for pod in pods:
                title_elem = pod.select_one("h3 a")
                name = (
                    title_elem["title"].strip()
                    if title_elem and "title" in title_elem.attrs
                    else (title_elem.text.strip() if title_elem else "")
                )
                if not name:
                    logger.warning(f"[{self.competitor_name}] Ürün başlığı bulunamadığı için kayıt atlandı.")
                    continue

                href = title_elem["href"].strip() if title_elem and "href" in title_elem.attrs else ""
                full_url = urljoin(page_url, href)

                price_elem = pod.select_one("p.price_color")
                raw_price_str = price_elem.text.strip() if price_elem else None

                tl_price = parse_and_validate_price(
                    raw_price_str,
                    multiplier=self.exchange_rate,
                    product_name=name,
                    source_name=self.competitor_name,
                )
                if tl_price is None:
                    continue

                stock_elem = pod.select_one("p.instock.availability")
                in_stock = ("in stock" in stock_elem.text.lower()) if stock_elem else True

                products.append({
                    "name": name,
                    "price": tl_price,
                    "in_stock": in_stock,
                    "url": full_url,
                })

            if page < max_pages:
                time.sleep(self.request_delay)

        if not products:
            raise RuntimeError(
                f"{self.competitor_name} üzerinden hiçbir geçerli ürün çekilemedi."
            )

        print(f"✓ Toplam {len(products)} geçerli ürün başarıyla çekildi.")
        return products

    def close(self):
        self.client.close()


def save_snapshots_to_db(db: Session, scraped_products: List[Dict[str, Any]]) -> int:
    """
    Çekilen ürünleri doğrulama ve aynı gün mükerrer kayıt engelleme ile price_snapshots tablosuna kaydeder.
    """
    return save_validated_snapshots_to_db(
        db=db,
        competitor_name=BooksToScrapeAdapter.COMPETITOR_NAME,
        base_url=BooksToScrapeAdapter.BASE_URL,
        scraped_products=scraped_products,
    )


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
        finally:
            session.close()
    finally:
        adapter.close()
