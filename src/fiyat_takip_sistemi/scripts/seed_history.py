import random
import sys
from datetime import datetime, time as dt_time, timedelta

from sqlalchemy import desc
from sqlalchemy.orm import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ..core.db import SessionLocal
from ..core.models import Competitor, Match, PriceSnapshot, Product


def seed_price_history(db: Session, days: int = 14) -> int:
    """
    Kılavuz Gün 3 (14:30-17:00 Ürün detay sayfası ve fiyat geçmişi):
    Son 14 gün için gerçekçi, küçük dalgalanmalı örnek fiyat geçmişi kayıtları üretir.
    Not: Bu veriler yalnızca demo gösterimi amaçlı örnek geçmiş verisidir.
    İdempotent çalışır: Aynı gün için zaten kayıt varsa tekrar eklemez.
    """
    random.seed(42)  # Tekrarlanabilir, tutarlı demo grafikleri için sabit tohum

    matches = (
        db.query(Match)
        .filter(Match.durum.in_(["otomatik_onayli", "onayli"]))
        .all()
    )
    competitors = {c.id: c.ad for c in db.query(Competitor).all()}
    products = {p.id: p for p in db.query(Product).all()}

    now = datetime.utcnow()
    today_date = now.date()
    inserted_count = 0

    print("=" * 80)
    print(f"📈 [ÖRNEK GEÇMİŞ VERİSİ] Son {days} gün için demo fiyat geçmişi üretiliyor...")
    print("=" * 80)

    for match in matches:
        latest_snap = (
            db.query(PriceSnapshot)
            .filter(
                PriceSnapshot.competitor_id == match.competitor_id,
                PriceSnapshot.ham_urun_adi == match.ham_urun_adi,
            )
            .order_by(desc(PriceSnapshot.cekilme_zamani), desc(PriceSnapshot.id))
            .first()
        )

        if not latest_snap:
            continue

        current_price = latest_snap.fiyat
        anchor_date = (
            latest_snap.cekilme_zamani.date()
            if latest_snap.cekilme_zamani
            else today_date
        )
        product = products.get(match.product_id)
        my_price = product.fiyat if product else current_price
        comp_name = competitors.get(match.competitor_id, "")
        is_fake_store = "Sahte Magaza" in comp_name or "Rakip C" in comp_name

        for days_ago in range(days, 0, -1):
            target_date = anchor_date - timedelta(days=days_ago)
            day_start = datetime.combine(target_date, dt_time.min)
            day_end = datetime.combine(target_date, dt_time.max)

            # O gün için bu rakip ve üründe kayıt var mı kontrol et
            existing = (
                db.query(PriceSnapshot)
                .filter(
                    PriceSnapshot.competitor_id == match.competitor_id,
                    PriceSnapshot.ham_urun_adi == match.ham_urun_adi,
                    PriceSnapshot.cekilme_zamani >= day_start,
                    PriceSnapshot.cekilme_zamani <= day_end,
                )
                .first()
            )
            if existing:
                continue

            if is_fake_store:
                # Rakip C için hikaye: İlk 9 gün bizim fiyatımıza yakın/biraz üstünde seyrederken
                # son 5 günde kademeli/agresif indirimle güncel fiyata düşer.
                if days_ago >= 6:
                    base_price = max(current_price * 1.10, my_price * 1.02)
                    noise = random.uniform(-0.015, 0.015)
                    hist_price = round(base_price * (1.0 + noise), 2)
                elif days_ago >= 3:
                    mid_price = (current_price + my_price) / 2.0
                    noise = random.uniform(-0.01, 0.01)
                    hist_price = round(mid_price * (1.0 + noise), 2)
                else:
                    noise = random.uniform(-0.005, 0.01)
                    hist_price = round(current_price * (1.0 + noise), 2)
            else:
                # Rakip A ve Rakip B için: Kur/kampanya kaynaklı %1 - %3 arası yumuşak dalgalanma
                wave = random.uniform(-0.025, 0.03)
                hist_price = round(current_price * (1.0 + wave), 2)

            hist_price = max(10.0, hist_price)
            snap_time = datetime.combine(target_date, dt_time(hour=9, minute=0, second=0))

            new_snap = PriceSnapshot(
                competitor_id=match.competitor_id,
                ham_urun_adi=match.ham_urun_adi,
                url=latest_snap.url,
                fiyat=hist_price,
                stokta=True,
                cekilme_zamani=snap_time,
            )
            db.add(new_snap)
            inserted_count += 1

    db.commit()
    print(f"✓ Toplam {inserted_count} adet örnek geçmiş fiyat kaydı eklendi.")
    print("ℹ️ Not: Üretilen bu kayıtlar demo sunumu için 'örnek demo verisi'dir.")
    return inserted_count


if __name__ == "__main__":
    session = SessionLocal()
    try:
        seed_price_history(session, days=14)
    finally:
        session.close()
