import sys
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

    def _clean_price(self, raw_price_text: str) -> float:
        """
        Fiyat metnindeki 'TL', para birimi ve boşlukları temizleyerek float değere çevirir.
        """
        cleaned = (
            raw_price_text.replace("TL", "")
            .replace("₺", "")
            .replace(",", ".")
            .strip()
        )
        return float(cleaned)

    def fetch_products(self) -> List[Dict[str, Any]]:
        """
        Sahte mağazadan /products sayfasını HTML olarak çeker ve ayrıştırır.
        """
        try:
            resp = self.client.get(self.products_url)
            resp.raise_for_status()
        except Exception as e:
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
            name = title_elem.text.strip() if title_elem else "Bilinmeyen Ürün"

            price_elem = card.select_one(".product-price")
            raw_price = price_elem.text.strip() if price_elem else "0"
            price = self._clean_price(raw_price)

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

        print(f"✓ {self.competitor_name} üzerinden {len(products)} ürün başarıyla çekildi.")
        return products

    def close(self):
        self.client.close()


def save_snapshots_to_db(db: Session, scraped_products: List[Dict[str, Any]]) -> int:
    """
    Çekilen sahte mağaza ürünlerini price_snapshots tablosuna kaydeder.
    """
    competitor = (
        db.query(Competitor)
        .filter(Competitor.ad == FakeStoreAdapter.COMPETITOR_NAME)
        .first()
    )
    if not competitor:
        competitor = Competitor(
            ad=FakeStoreAdapter.COMPETITOR_NAME,
            base_url=FakeStoreAdapter.BASE_URL,
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
    adapter = FakeStoreAdapter()
    try:
        scraped = adapter.fetch_products()
        session = SessionLocal()
        try:
            saved = save_snapshots_to_db(session, scraped)
            total = (
                session.query(PriceSnapshot)
                .filter(PriceSnapshot.competitor_id == 2)
                .count()
            )
            print(f"✓ price_snapshots tablosuna {saved} yeni Rakip C kaydı yazıldı.")
            print(f"✓ Veritabanındaki toplam Rakip C snapshot sayısı: {total}")

            # Örnek ilk 3 kayıt
            print("\nÖrnek Fiyat Kayıtları (İlk 3 Ürün):")
            sample = (
                session.query(PriceSnapshot)
                .filter(PriceSnapshot.competitor_id == 2)
                .order_by(PriceSnapshot.id.desc())
                .limit(3)
                .all()
            )
            for s in reversed(sample):
                print(f"  • {s.ham_urun_adi} -> {s.fiyat:.2f} TL | Stokta: {s.stokta} | URL: {s.url}")
        finally:
            session.close()
    finally:
        adapter.close()
