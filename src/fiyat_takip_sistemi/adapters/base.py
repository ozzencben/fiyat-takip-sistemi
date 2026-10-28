from abc import ABC, abstractmethod
from datetime import datetime, time as dt_time
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..core.logger import get_logger
from ..core.models import Competitor, PriceSnapshot

logger = get_logger("adapters")


class BaseAdapter(ABC):
    """
    Tüm rakip site adaptörleri için temel sözleşme (Interface).
    Her adaptör fetch_products() metodunu uygulayarak standart bir ürün listesi döndürmelidir.
    """

    def __init__(self, competitor_name: str, base_url: str):
        self.competitor_name = competitor_name
        self.base_url = base_url

    @abstractmethod
    def fetch_products(self) -> List[Dict[str, Any]]:
        """
        Rakip siteden ürünleri çeker ve standart formatta bir liste döndürür.
        Her eleman şu anahtarları içermelidir:
            - name (str): Ürünün ham adı
            - price (float): Ürünün fiyatı (TL cinsinden)
            - in_stock (bool): Stokta olup olmadığı
            - url (str): Ürünün doğrudan tam URL adresi
        """
        pass


def parse_and_validate_price(
    raw_price: Optional[str],
    multiplier: float = 1.0,
    product_name: str = "Bilinmeyen Ürün",
    source_name: str = "Adaptör",
) -> Optional[float]:
    """
    Kılavuz gereksinimi (Gün 2 19:30-22:00 Sağlamlaştırma):
    Fiyat bulunamazsa, sayıya çevrilemezse, 0 veya negatif çıkarsa kaydı atlar ve loglar.
    Geçerli ise TL karşılığını (float) döndürür.
    """
    if raw_price is None or not str(raw_price).strip():
        logger.warning(f"[{source_name}] Fiyat bulunamadığı için kayıt atlandı: '{product_name}'")
        return None

    cleaned = (
        str(raw_price)
        .replace("£", "")
        .replace("Â", "")
        .replace("$", "")
        .replace("TL", "")
        .replace("₺", "")
        .replace(",", ".")
        .strip()
    )

    try:
        numeric_price = float(cleaned)
    except ValueError:
        logger.warning(
            f"[{source_name}] Fiyat metni ('{raw_price}') sayıya çevrilemediği için atlandı: '{product_name}'"
        )
        return None

    final_price = round(numeric_price * multiplier, 2)
    if final_price <= 0:
        logger.warning(
            f"[{source_name}] Fiyat 0 veya negatif ({final_price} TL) olduğu için kayıt atlandı: '{product_name}'"
        )
        return None

    return final_price


def save_validated_snapshots_to_db(
    db: Session,
    competitor_name: str,
    base_url: str,
    scraped_products: List[Dict[str, Any]],
) -> int:
    """
    Kılavuz gereksinimi (Gün 2 19:30-22:00 Sağlamlaştırma):
    - Fiyatı 0, negatif veya eksik olan kayıtları atlar ve loglar.
    - Aynı gün içinde aynı ürünün (aynı fiyatla) iki kez kaydedilmesini engeller.
    """
    competitor = db.query(Competitor).filter(Competitor.ad == competitor_name).first()
    if not competitor:
        competitor = Competitor(ad=competitor_name, base_url=base_url)
        db.add(competitor)
        db.commit()
        db.refresh(competitor)

    now = datetime.utcnow()
    today_start = datetime.combine(now.date(), dt_time.min)
    today_end = datetime.combine(now.date(), dt_time.max)

    saved_count = 0
    skipped_duplicate_count = 0
    skipped_invalid_count = 0

    for item in scraped_products:
        name = str(item.get("name", "")).strip()
        price = item.get("price")

        if not name:
            logger.warning(f"[{competitor_name}] Ürün adı boş olduğu için kayıt atlandı.")
            skipped_invalid_count += 1
            continue

        if price is None or not isinstance(price, (int, float)) or float(price) <= 0:
            logger.warning(
                f"[{competitor_name}] Geçersiz fiyat ({price}) nedeniyle veritabanı kaydı atlandı: '{name}'"
            )
            skipped_invalid_count += 1
            continue

        price_val = round(float(price), 2)

        # Aynı gün aynı ürünün tekrar kaydedilmesini kontrol et
        existing_today = (
            db.query(PriceSnapshot)
            .filter(
                PriceSnapshot.competitor_id == competitor.id,
                PriceSnapshot.ham_urun_adi == name,
                PriceSnapshot.cekilme_zamani >= today_start,
                PriceSnapshot.cekilme_zamani <= today_end,
            )
            .order_by(desc(PriceSnapshot.id))
            .first()
        )

        if existing_today is not None and round(existing_today.fiyat, 2) == price_val:
            skipped_duplicate_count += 1
            continue

        snapshot = PriceSnapshot(
            competitor_id=competitor.id,
            ham_urun_adi=name,
            url=str(item.get("url", base_url)),
            fiyat=price_val,
            stokta=bool(item.get("in_stock", True)),
            cekilme_zamani=now,
        )
        db.add(snapshot)
        saved_count += 1

    db.commit()

    if skipped_duplicate_count > 0:
        logger.info(
            f"[{competitor_name}] Aynı gün içinde mükerrer olan {skipped_duplicate_count} ürün kaydı atlandı."
        )
    if skipped_invalid_count > 0:
        logger.warning(
            f"[{competitor_name}] Hatalı/geçersiz {skipped_invalid_count} ürün kaydı atlandı."
        )

    return saved_count
