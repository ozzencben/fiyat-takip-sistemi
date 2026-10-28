import sys
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from sqlalchemy import desc
from sqlalchemy.orm import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .db import SessionLocal
from .models import Competitor, Match, PriceSnapshot, Product


class Severity(str, Enum):
    YUKSEK = "YÜKSEK"
    ORTA = "ORTA"
    DUSUK = "DÜŞÜK"


class RuleType(str, Enum):
    RAKIP_UCUZ = "RAKIP_UCUZ"
    FIYAT_DUSTU = "FIYAT_DUSTU"
    STOK_BITTI = "STOK_BITTI"
    ONERI = "ONERI"


@dataclass
class Alert:
    rule_type: RuleType
    severity: Severity
    product_sku: str
    product_name: str
    competitor_name: str
    current_my_price: float
    current_comp_price: float
    cost: float
    min_margin_pct: float
    message: str
    recommendation: Optional[str] = None
    suggested_price: Optional[float] = None


def evaluate_rules(db: Session) -> List[Alert]:
    """
    Kılavuz gereksinimi:
    Tüm onaylı eşleşmeler için kuralları çalıştırır ve önceliklendirilmiş uyarı listesi üretir.
    - RAKIP_UCUZ: Rakip fiyatı senin fiyatından düşük.
    - FIYAT_DUSTU: Rakip fiyatı bir önceki kayda göre %5 veya daha fazla düştü.
    - STOK_BITTI: Rakipte ürün stokta yok (fırsat).
    - ONERI: Rakip fiyatı - %1, min marj kontrolü ile ('marjı bozmadan rekabet edemezsin').
    """
    alerts: List[Alert] = []

    # Onaylı veya otomatik onaylı eşleşmeleri getir
    matches = (
        db.query(Match)
        .filter(Match.durum.in_(["otomatik_onayli", "onayli"]))
        .all()
    )

    for match in matches:
        product = db.query(Product).filter(Product.id == match.product_id).first()
        competitor = db.query(Competitor).filter(Competitor.id == match.competitor_id).first()

        if not product or not competitor:
            continue

        # Rakibin bu ürün için kaydettiği son 2 snapshot'ı al (fiyat değişimi tespiti için)
        snapshots = (
            db.query(PriceSnapshot)
            .filter(
                PriceSnapshot.competitor_id == competitor.id,
                PriceSnapshot.ham_urun_adi == match.ham_urun_adi,
            )
            .order_by(desc(PriceSnapshot.id))
            .limit(2)
            .all()
        )

        if not snapshots:
            continue

        latest_snap = snapshots[0]
        prev_snap = snapshots[1] if len(snapshots) > 1 else None

        # ---------------------------------------------------------------------
        # 1. KURAL: STOK_BITTI (Fırsat Uyarısı)
        # ---------------------------------------------------------------------
        if not latest_snap.stokta:
            alerts.append(
                Alert(
                    rule_type=RuleType.STOK_BITTI,
                    severity=Severity.ORTA,
                    product_sku=product.sku,
                    product_name=product.urun_adi,
                    competitor_name=competitor.ad,
                    current_my_price=product.fiyat,
                    current_comp_price=latest_snap.fiyat,
                    cost=product.maliyet,
                    min_margin_pct=product.min_marj_yuzde,
                    message="Rakipte ürünün stoğu bitti. Bu bir fırsat uyarısıdır: Fiyatınızı koruyabilir veya marjınızı artırabilirsiniz.",
                    recommendation="Fiyatı düşürme; stok avantajını kullanarak mevcut fiyatı koru.",
                )
            )

        # ---------------------------------------------------------------------
        # 2. KURAL: FIYAT_DUSTU (Önceki kayda göre %5 veya daha fazla düşüş)
        # ---------------------------------------------------------------------
        if prev_snap and prev_snap.fiyat > 0:
            price_drop = prev_snap.fiyat - latest_snap.fiyat
            drop_pct = (price_drop / prev_snap.fiyat) * 100.0

            if drop_pct >= 5.0:
                alerts.append(
                    Alert(
                        rule_type=RuleType.FIYAT_DUSTU,
                        severity=Severity.YUKSEK,
                        product_sku=product.sku,
                        product_name=product.urun_adi,
                        competitor_name=competitor.ad,
                        current_my_price=product.fiyat,
                        current_comp_price=latest_snap.fiyat,
                        cost=product.maliyet,
                        min_margin_pct=product.min_marj_yuzde,
                        message=f"Rakip fiyatı önceki kayda göre %{drop_pct:.1f} düştü ({prev_snap.fiyat:.2f} TL ➔ {latest_snap.fiyat:.2f} TL).",
                        recommendation="Rakip agresif indirim uyguladı, rekabetçi fiyat önerisini inceleyin.",
                    )
                )

        # ---------------------------------------------------------------------
        # 3. KURAL & 4. KURAL: RAKIP_UCUZ ve ONERI
        # ---------------------------------------------------------------------
        if latest_snap.fiyat < product.fiyat:
            diff_tl = product.fiyat - latest_snap.fiyat
            diff_pct = (diff_tl / product.fiyat) * 100.0

            # Kılavuz kuralı: Rakibe yetişmek için önerilen fiyat = rakip fiyatı eksi %1
            suggested_price = round(latest_snap.fiyat * 0.99, 2)

            # Minimum kabul edilebilir fiyat: maliyet × (1 + min_marj)
            min_allowed_price = round(product.maliyet * (1.0 + product.min_marj_yuzde / 100.0), 2)

            if suggested_price < min_allowed_price:
                severity = Severity.YUKSEK
                rec_text = (
                    f"Marjı bozmadan rekabet edemezsin. "
                    f"(Önerilen Fiyat: {suggested_price:.2f} TL < Min Fiyat: {min_allowed_price:.2f} TL | "
                    f"Maliyet: {product.maliyet:.2f} TL, Hedef Marj: %{product.min_marj_yuzde:.0f})"
                )
            else:
                severity = Severity.YUKSEK if diff_pct >= 15.0 else Severity.ORTA
                calculated_margin = ((suggested_price - product.maliyet) / product.maliyet) * 100.0
                rec_text = (
                    f"Önerilen Fiyat: {suggested_price:.2f} TL "
                    f"(Rakibin %1 altı, %{calculated_margin:.1f} güvenli kar marjı korunur)."
                )

            alerts.append(
                Alert(
                    rule_type=RuleType.RAKIP_UCUZ,
                    severity=severity,
                    product_sku=product.sku,
                    product_name=product.urun_adi,
                    competitor_name=competitor.ad,
                    current_my_price=product.fiyat,
                    current_comp_price=latest_snap.fiyat,
                    cost=product.maliyet,
                    min_margin_pct=product.min_marj_yuzde,
                    message=f"Rakip fiyatı ({latest_snap.fiyat:.2f} TL) senin fiyatından ({product.fiyat:.2f} TL) {diff_tl:.2f} TL (%{diff_pct:.1f}) daha düşük.",
                    recommendation=rec_text,
                    suggested_price=suggested_price,
                )
            )

    # Öncelik sırasına göre sırala: YÜKSEK -> ORTA -> DÜŞÜK
    priority_order = {Severity.YUKSEK: 1, Severity.ORTA: 2, Severity.DUSUK: 3}
    alerts.sort(key=lambda a: priority_order.get(a.severity, 99))

    return alerts


def print_alerts_summary(alerts: List[Alert]) -> None:
    """Uyarı listesini terminalde şık ve okunaklı bir şekilde yazdırır."""
    print("\n" + "=" * 90)
    print("🚨 [KURAL MOTORU UYARI VE AKSİYON RAPORU]")
    print(f"Toplam Üretilen Uyarı Sayısı: {len(alerts)}")
    print("=" * 90)

    if not alerts:
        print("✓ Herhangi bir kritik fiyat veya stok uyarısı bulunmamaktadır.")
        return

    for idx, alert in enumerate(alerts, 1):
        icon = "🔴" if alert.severity == Severity.YUKSEK else ("🟡" if alert.severity == Severity.ORTA else "🔵")
        print(f"\n{icon} [{idx}] [{alert.severity.value}] {alert.rule_type.value} | {alert.product_name}")
        print(f"   • Rakip        : {alert.competitor_name}")
        print(f"   • Fiyatlar     : Bizim: {alert.current_my_price:.2f} TL | Rakip: {alert.current_comp_price:.2f} TL")
        print(f"   • Durum        : {alert.message}")
        if alert.recommendation:
            print(f"   • 💡 Tavsiye   : {alert.recommendation}")
        print("-" * 90)


if __name__ == "__main__":
    session = SessionLocal()
    try:
        active_alerts = evaluate_rules(session)
        print_alerts_summary(active_alerts)
    finally:
        session.close()
