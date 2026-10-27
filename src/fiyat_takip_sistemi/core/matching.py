import re
import sys
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .db import SessionLocal
from .models import Competitor, Match, PriceSnapshot, Product

# Kılavuz gereksinimi: Eşikler kodda sabit bir yerde tanımlanır
THRESHOLD_AUTO_APPROVE: float = 90.0  # 90 ve üzeri: otomatik onaylı
THRESHOLD_REVIEW: float = 70.0        # 70 - 89 arası: onay bekliyor
                                      # 70 altı: eşleşme yok


def normalize_product_name(name: str) -> str:
    """
    Kılavuz gereksinimi:
    İsimleri normalize et (küçük harf, noktalama işaretleri ve parantez içlerini temizle).
    """
    if not name:
        return ""

    # Küçük harfe çevir
    text = name.lower()

    # Parantez ve köşeli parantez içlerini temizle (örn: (Ciltli), [Roman] vb.)
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)

    # Noktalama işaretlerini ve özel karakterleri temizle (boşluk bırakarak)
    text = re.sub(r"[^\w\s]", " ", text)

    # Fazla boşlukları teke indir ve baştaki/sondaki boşlukları kaldır
    text = re.sub(r"\s+", " ", text).strip()

    return text


def find_best_match(
    product_name: str, candidate_titles: List[str]
) -> Tuple[Optional[str], float]:
    """
    rapidfuzz token_set_ratio kullanarak bir ürün için aday başlıklar arasındaki
    en yüksek benzerlik skoruna sahip başlığı ve skoru bulur.
    """
    normalized_target = normalize_product_name(product_name)
    best_candidate: Optional[str] = None
    best_score: float = 0.0

    for candidate in candidate_titles:
        normalized_candidate = normalize_product_name(candidate)
        score = float(fuzz.token_set_ratio(normalized_target, normalized_candidate))

        if score > best_score:
            best_score = score
            best_candidate = candidate

    return best_candidate, round(best_score, 1)


def run_product_matching(db: Session) -> Dict[str, int]:
    """
    Tüm ürünleri tüm aktif rakiplerdeki güncel snapshot başlıklarıyla eşleştirir
    ve sonuçları matches tablosuna idempotent olarak yazar.
    """
    products = db.query(Product).all()
    competitors = db.query(Competitor).all()

    stats = {
        "otomatik_onayli": 0,
        "onay_bekliyor": 0,
        "eslesme_yok": 0,
        "toplam_kontrol": 0,
    }

    print("=" * 80)
    print("🔍 [ÜRÜN EŞLEŞTİRME] Rapidfuzz (token_set_ratio) Çalıştırılıyor...")
    print(f"Sabit Eşikler -> Otomatik Onay: >={THRESHOLD_AUTO_APPROVE} | Onay Bekliyor: >={THRESHOLD_REVIEW}")
    print("=" * 80)

    for competitor in competitors:
        # İlgili rakibin snapshot tablosundaki benzersiz ürün isimlerini al
        candidate_rows = (
            db.query(PriceSnapshot.ham_urun_adi)
            .filter(PriceSnapshot.competitor_id == competitor.id)
            .distinct()
            .all()
        )
        candidate_titles = [row[0] for row in candidate_rows if row[0]]

        if not candidate_titles:
            print(f"⚠️ {competitor.ad} için snapshot kaydı bulunamadı, atlanıyor.")
            continue

        print(f"\n📌 Rakip: {competitor.ad} ({len(candidate_titles)} benzersiz ürün inceleniyor)")
        print("-" * 80)

        for product in products:
            stats["toplam_kontrol"] += 1
            best_title, best_score = find_best_match(product.urun_adi, candidate_titles)

            durum: Optional[str] = None
            if best_score >= THRESHOLD_AUTO_APPROVE:
                durum = "otomatik_onayli"
                stats["otomatik_onayli"] += 1
            elif best_score >= THRESHOLD_REVIEW:
                durum = "onay_bekliyor"
                stats["onay_bekliyor"] += 1
            else:
                stats["eslesme_yok"] += 1

            # 70 altı ise kılavuz gereği matches tablosuna yazılmaz
            if durum and best_title:
                # Idempotent kayıt kontrolü
                existing_match = (
                    db.query(Match)
                    .filter(
                        Match.product_id == product.id,
                        Match.competitor_id == competitor.id,
                    )
                    .first()
                )

                if existing_match:
                    # Manuel 'onayli' veya 'reddedildi' kararı verilmemişse güncelle
                    if existing_match.durum in ["otomatik_onayli", "onay_bekliyor"]:
                        existing_match.ham_urun_adi = best_title
                        existing_match.skor = best_score
                        existing_match.durum = durum
                else:
                    new_match = Match(
                        product_id=product.id,
                        competitor_id=competitor.id,
                        ham_urun_adi=best_title,
                        skor=best_score,
                        durum=durum,
                    )
                    db.add(new_match)

                durum_ikon = "✅" if durum == "otomatik_onayli" else "⏳"
                print(
                    f"{durum_ikon} {durum:<16} | Skor: %{best_score:>4.0f} | "
                    f"Bizim: {product.urun_adi[:28]:<28} ➔ Rakip: {best_title[:28]}"
                )
            else:
                print(
                    f"❌ {'eslesme_yok':<16} | Skor: %{best_score:>4.0f} | "
                    f"Bizim: {product.urun_adi[:28]:<28} ➔ En Yakın: {str(best_title)[:28]}"
                )

    db.commit()

    print("\n" + "=" * 80)
    print("📊 [EŞLEŞTİRME ÖZET RAPORU]")
    print(f"  • Toplam İncelenen Çift   : {stats['toplam_kontrol']}")
    print(f"  • Otomatik Onaylanan (>=90) : {stats['otomatik_onayli']}")
    print(f"  • Onay Bekleyen (70-89)    : {stats['onay_bekliyor']}")
    print(f"  • Eşleşme Bulunamayan (<70): {stats['eslesme_yok']}")
    print("=" * 80 + "\n")

    return stats


if __name__ == "__main__":
    session = SessionLocal()
    try:
        results = run_product_matching(session)
    finally:
        session.close()
