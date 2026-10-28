import sys
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

logger = get_logger("fake_store")


class FakeStoreAdapter(BaseAdapter):
    """
    Rakip C (Sahte Mağaza - localhost:8001) adaptörü.
    FastAPI tarafından sunulan HTML ürün kartlarını çekip ayrıştırır.
    """

    COMPETITOR_NAME = "Rakip C (Sahte Magaza)"
    BASE_URL = "http://localhost:8001"
    PRODUCTS_URL = "http://localhost:8001/products"

    def __init__(self, base_url: str = BASE_URL):
        super().__init__(competitor_name=self.COMPETITOR_NAME, base_url=base_url)
        self.products_url = f"{base_url.rstrip('/')}/products"
        self.client = httpx.Client(timeout=10.0)

    def fetch_products(self) -> List[Dict[str, Any]]:
        """
        Sahte mağazadan /products sayfasını HTML olarak çeker ve ayrıştırır.
        Sayfa açılmazsa, fiyat bulunamazsa veya 0/negatif çıkarsa kaydı atlar ve loglar.
        """
        try:
            resp = self.client.get(self.products_url)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[{self.competitor_name}] Sayfa açılamadı ({self.products_url}): {e}")
            raise ConnectionError(
                f"Sahte mağazaya ({self.products_url}) bağlanılamadı. "
                f"Lütfen 'fake_store/main.py' sunucusunun port 8001'de çalıştığından emin olun. Hata: {e}"
            )

        html_content = resp.content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html_content, "html.parser")
        cards = soup.select(".product-card")

        products: List[Dict[str, Any]] = []
        for card in cards:
            title_elem = card.select_one(".product-title")
            name = title_elem.text.strip() if title_elem else ""
            if not name:
                logger.warning(f"[{self.competitor_name}] Ürün başlığı boş olduğu için kart atlandı.")
                continue

            price_elem = card.select_one(".product-price")
            raw_price = price_elem.text.strip() if price_elem else None
            price = parse_and_validate_price(
                raw_price,
                multiplier=1.0,
                product_name=name,
                source_name=self.competitor_name,
            )
            if price is None:
                continue

            stock_elem = card.select_one(".product-stock")
            in_stock = ("stokta var" in stock_elem.text.lower()) if stock_elem else True

            link_elem = card.select_one(".product-link")
            raw_href = link_elem["href"].strip() if link_elem and "href" in link_elem.attrs else ""
            full_url = urljoin(self.base_url, raw_href)

            products.append({
                "name": name,
                "price": price,
                "in_stock": in_stock,
                "url": full_url,
            })

        if not products:
            raise RuntimeError(
                f"{self.competitor_name} üzerinden hiçbir geçerli ürün çekilemedi."
            )

        print(f"✓ {self.competitor_name} üzerinden {len(products)} geçerli ürün başarıyla çekildi.")
        return products

    def close(self):
        self.client.close()


def save_snapshots_to_db(db: Session, scraped_products: List[Dict[str, Any]]) -> int:
    """
    Çekilen sahte mağaza ürünlerini doğrulama ve aynı gün mükerrer kayıt engelleme ile price_snapshots tablosuna kaydeder.
    """
    return save_validated_snapshots_to_db(
        db=db,
        competitor_name=FakeStoreAdapter.COMPETITOR_NAME,
        base_url=FakeStoreAdapter.BASE_URL,
        scraped_products=scraped_products,
    )


if __name__ == "__main__":
    adapter = FakeStoreAdapter()
    try:
        scraped = adapter.fetch_products()
        session = SessionLocal()
        try:
            saved = save_snapshots_to_db(session, scraped)
            print(f"✓ price_snapshots tablosuna {saved} yeni Rakip C kaydı yazıldı.")
        finally:
            session.close()
    finally:
        adapter.close()
