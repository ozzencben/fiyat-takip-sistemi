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
from .base import (
    BaseAdapter,
    parse_and_validate_price,
    save_validated_snapshots_to_db,
)

logger = get_logger("webscraper_io")

# Kılavuz gereksinimi: Rakip B (webscraper.io) için sabit USD -> TL kur çarpanı (1 $ = 35 TL)
KUR_USD_TL: float = 35.0


class WebScraperIOAdapter(BaseAdapter):
    """
    Kılavuz Gün 2 (19:30-22:00):
    Rakip B adaptörü (webscraper.io e-ticaret test sayfaları).
    Farklı bir HTML şeması (div.card.thumbnail, a.title, .price) üzerinden
    elektronik ürün fiyatlarını çeker.
    """

    COMPETITOR_NAME = "Rakip B (WebScraper.io)"
    BASE_URL = "https://webscraper.io"
    CATEGORY_URLS = [
        "https://webscraper.io/test-sites/e-commerce/allinone/computers/tablets",
        "https://webscraper.io/test-sites/e-commerce/allinone/phones/touch",
    ]

    def __init__(self, exchange_rate: float = KUR_USD_TL, request_delay: float = 1.0):
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
        """Kazımaya başlamadan önce robots.txt dosyasını kontrol eder."""
        robots_url = urljoin(self.base_url, "/robots.txt")
        try:
            resp = self.client.get(robots_url)
            print(f"[Robots.txt - WebScraper.io] Durum Kodu: {resp.status_code}")
        except Exception as e:
            logger.warning(f"[Robots.txt - WebScraper.io] Kontrol edilirken uyarı: {e}")

    def _fetch_page_with_retry(self, url: str, max_retries: int = 3) -> str | None:
        """Hata durumunda 2-3 kez yeniden deneyen güvenli HTTP GET isteği."""
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.client.get(url)
                if resp.status_code == 200:
                    return resp.content.decode("utf-8", errors="replace")
                logger.warning(
                    f"[{self.competitor_name}] Sayfa hatası: {url} -> HTTP {resp.status_code} (Deneme {attempt}/{max_retries})"
                )
            except Exception as e:
                logger.warning(
                    f"[{self.competitor_name}] Bağlantı hatası: {url} çekilemedi: {e} (Deneme {attempt}/{max_retries})"
                )
            if attempt < max_retries:
                time.sleep(self.request_delay * attempt)
        return None

    def fetch_products(self) -> List[Dict[str, Any]]:
        """
        webscraper.io test sayfalarından elektronik ürünleri çeker.
        Sayfa açılmazsa, fiyat bulunamazsa veya 0/negatif çıkarsa kaydı atlar ve loglar.
        """
        self.check_robots_txt()
        products: List[Dict[str, Any]] = []

        print(f"🚀 {self.competitor_name} üzerinden elektronik ürün çekimi başlıyor...")

        for idx, url in enumerate(self.CATEGORY_URLS, 1):
            print(f"📄 Kategori {idx}/{len(self.CATEGORY_URLS)} çekiliyor: {url}")
            html_content = self._fetch_page_with_retry(url)
            if not html_content:
                logger.warning(f"[{self.competitor_name}] Sayfa açılamadığı için atlandı: {url}")
                continue

            soup = BeautifulSoup(html_content, "html.parser")
            cards = soup.select("div.card.thumbnail")

            for card in cards:
                title_elem = card.select_one("a.title")
                name = (
                    title_elem.get("title", "").strip()
                    if title_elem and title_elem.get("title")
                    else (title_elem.text.strip() if title_elem else "")
                )
                if not name:
                    logger.warning(f"[{self.competitor_name}] Ürün adı bulunamadığı için kayıt atlandı.")
                    continue

                href = title_elem.get("href", "").strip() if title_elem else ""
                full_url = urljoin(self.base_url, href)

                price_elem = card.select_one(".price, h4.price, span[itemprop='price']")
                raw_price_str = price_elem.text.strip() if price_elem else None

                tl_price = parse_and_validate_price(
                    raw_price_str,
                    multiplier=self.exchange_rate,
                    product_name=name,
                    source_name=self.competitor_name,
                )
                if tl_price is None:
                    continue

                products.append({
                    "name": name,
                    "price": tl_price,
                    "in_stock": True,
                    "url": full_url,
                })

            if idx < len(self.CATEGORY_URLS):
                time.sleep(self.request_delay)

        if not products:
            raise RuntimeError(
                f"{self.competitor_name} üzerinden hiçbir geçerli ürün çekilemedi."
            )

        print(f"✓ {self.competitor_name} üzerinden {len(products)} geçerli elektronik ürün çekildi.")
        return products

    def close(self):
        self.client.close()


def save_snapshots_to_db(db: Session, scraped_products: List[Dict[str, Any]]) -> int:
    """
    Çekilen Rakip B ürünlerini doğrulama ve aynı gün mükerrer kayıt engelleme ile price_snapshots tablosuna kaydeder.
    """
    return save_validated_snapshots_to_db(
        db=db,
        competitor_name=WebScraperIOAdapter.COMPETITOR_NAME,
        base_url=WebScraperIOAdapter.BASE_URL,
        scraped_products=scraped_products,
    )


if __name__ == "__main__":
    adapter = WebScraperIOAdapter()
    try:
        scraped = adapter.fetch_products()
        session = SessionLocal()
        try:
            saved = save_snapshots_to_db(session, scraped)
            print(f"✓ price_snapshots tablosuna {saved} yeni Rakip B kaydı yazıldı.")
        finally:
            session.close()
    finally:
        adapter.close()

