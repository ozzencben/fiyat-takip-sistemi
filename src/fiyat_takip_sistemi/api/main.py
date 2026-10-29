import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.models import Competitor, Match, PriceSnapshot, Product
from ..core.report import get_latest_report_text
from ..scripts.seed_history import seed_price_history

app = FastAPI(
    title="Fiyat Takip Sistemi - Web Paneli API",
    description="Rakip fiyat karşılaştırma, günlük LLM raporu ve fiyat geçmişi API uç noktaları.",
    version="1.0.0",
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _get_competitor_role_map(db: Session) -> Dict[int, str]:
    """Rakip ID'lerini Rakip A, Rakip B, Rakip C anahtarlarıyla eşleştirir."""
    role_map: Dict[int, str] = {}
    for comp in db.query(Competitor).all():
        ad_lower = comp.ad.lower()
        if "rakip a" in ad_lower or "bookstoscrape" in ad_lower:
            role_map[comp.id] = "rakip_a"
        elif "rakip b" in ad_lower or "webscraper" in ad_lower:
            role_map[comp.id] = "rakip_b"
        elif "rakip c" in ad_lower or "sahte magaza" in ad_lower:
            role_map[comp.id] = "rakip_c"
    return role_map


def _build_product_comparison_item(
    db: Session,
    product: Product,
    competitors_by_id: Dict[int, Competitor],
    role_map: Dict[int, str],
) -> Dict[str, Any]:
    """Tek bir ürün için onaylı rakip fiyatlarını, farkı ve fiyat önerisini hesaplar."""
    matches = (
        db.query(Match)
        .filter(
            Match.product_id == product.id,
            Match.durum.in_(["otomatik_onayli", "onayli"]),
        )
        .all()
    )

    rakip_prices_by_role: Dict[str, Optional[float]] = {
        "rakip_a": None,
        "rakip_b": None,
        "rakip_c": None,
    }
    competitor_details: List[Dict[str, Any]] = []

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

        comp = competitors_by_id.get(match.competitor_id)
        comp_name = comp.ad if comp else f"Rakip #{match.competitor_id}"
        role_key = role_map.get(match.competitor_id)
        if role_key:
            rakip_prices_by_role[role_key] = latest_snap.fiyat

        competitor_details.append({
            "competitor_id": match.competitor_id,
            "rakip_adi": comp_name,
            "ham_urun_adi": match.ham_urun_adi,
            "fiyat": latest_snap.fiyat,
            "stokta": latest_snap.stokta,
            "url": latest_snap.url,
            "cekilme_zamani": latest_snap.cekilme_zamani.strftime("%Y-%m-%d %H:%M:%S")
            if latest_snap.cekilme_zamani
            else None,
        })

    valid_prices = [c["fiyat"] for c in competitor_details if c["fiyat"] is not None]
    min_comp_price: Optional[float] = min(valid_prices) if valid_prices else None

    fark: Optional[float] = None
    fark_yuzde: Optional[float] = None
    durum = "VERİ YOK"
    onerilen_fiyat: Optional[float] = None
    oneri_notu: Optional[str] = None

    min_allowed_price = round(
        product.maliyet * (1.0 + product.min_marj_yuzde / 100.0), 2
    )

    if min_comp_price is not None:
        fark = round(min_comp_price - product.fiyat, 2)
        fark_yuzde = round((fark / product.fiyat) * 100.0, 1) if product.fiyat > 0 else 0.0

        if min_comp_price < product.fiyat:
            durum = "RAKİP UCUZ"
            candidate_price = round(min_comp_price * 0.99, 2)
            onerilen_fiyat = candidate_price
            if candidate_price < min_allowed_price:
                oneri_notu = (
                    f"Marjı bozmadan rekabet edemezsin "
                    f"(Önerilen: {candidate_price:.2f} TL < Min Fiyat: {min_allowed_price:.2f} TL)"
                )
            else:
                safe_margin = ((candidate_price - product.maliyet) / product.maliyet) * 100.0
                oneri_notu = (
                    f"Önerilen Fiyat: {candidate_price:.2f} TL (%{safe_margin:.1f} marj korunur)"
                )
        elif min_comp_price > product.fiyat:
            durum = "BİZ UCUZUZ"
            oneri_notu = "Fiyat avantajı bizde; mevcut fiyat korunabilir."
        else:
            durum = "EŞİT"
            oneri_notu = "Rakip ile fiyat eşit."

    return {
        "id": product.id,
        "sku": product.sku,
        "urun_adi": product.urun_adi,
        "benim_fiyatim": product.fiyat,
        "maliyet": product.maliyet,
        "min_marj_yuzde": product.min_marj_yuzde,
        "min_kabul_edilebilir_fiyat": min_allowed_price,
        "rakip_a": rakip_prices_by_role["rakip_a"],
        "rakip_b": rakip_prices_by_role["rakip_b"],
        "rakip_c": rakip_prices_by_role["rakip_c"],
        "en_dusuk_rakip_fiyat": min_comp_price,
        "fark": fark,
        "fark_yuzde": fark_yuzde,
        "durum": durum,
        "onerilen_fiyat": onerilen_fiyat,
        "oneri_notu": oneri_notu,
        "rakip_fiyatlari": competitor_details,
    }


@app.get("/", response_class=HTMLResponse, tags=["Web Paneli"])
def get_dashboard_home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """
    Kılavuz Gün 3 (11:00-13:30 Ana sayfa ve ürün tablosu):
    Üstte 3 özet kutusu, altında günün LLM raporu ve altında arama/filtre destekli
    ürün karşılaştırma tablosunu gösterir.
    """
    ozet_data = get_ozet(db=db)
    urunler_data = get_urunler(db=db)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "ozet": ozet_data,
            "urunler": urunler_data,
        },
    )


@app.get("/urun/{id}", response_class=HTMLResponse, tags=["Web Paneli"])
def get_product_detail_page(
    id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    """
    Kılavuz Gün 3 (14:30-17:00 Ürün detay sayfası ve fiyat geçmişi):
    Ürüne tıklayınca açılan sayfada Chart.js ile her rakip için bir çizgi ve
    kendi fiyatımız için sabit çizgi içeren 14 günlük fiyat geçmişi grafiğini gösterir.
    """
    gecmis_data = get_urun_gecmis(id=id, db=db)
    product = db.query(Product).filter(Product.id == id).first()
    competitors_by_id = {c.id: c for c in db.query(Competitor).all()}
    role_map = _get_competitor_role_map(db)
    karsilastirma = _build_product_comparison_item(
        db, product, competitors_by_id, role_map
    )

    return templates.TemplateResponse(
        request=request,
        name="product_detail.html",
        context={
            "detay": gecmis_data,
            "karsilastirma": karsilastirma,
        },
    )


def _serialize_match_row(
    db: Session,
    match: Match,
    products_by_id: Dict[int, Product],
    competitors_by_id: Dict[int, Competitor],
) -> Dict[str, Any]:
    """Tek bir eşleşme kaydını onay ekranı için zenginleştirir."""
    prod = products_by_id.get(match.product_id)
    comp = competitors_by_id.get(match.competitor_id)

    latest_snap = (
        db.query(PriceSnapshot)
        .filter(
            PriceSnapshot.competitor_id == match.competitor_id,
            PriceSnapshot.ham_urun_adi == match.ham_urun_adi,
        )
        .order_by(desc(PriceSnapshot.cekilme_zamani), desc(PriceSnapshot.id))
        .first()
    )

    if match.skor >= 80.0:
        oneri_metni = (
            f"Öneri: Aynı ürün (Benzerlik %{match.skor:.0f}, alt başlık/kısaltma farkı görünüyor)"
        )
    else:
        oneri_metni = (
            f"Öneri: Kontrol edin (Benzerlik %{match.skor:.0f}, anahtar kelimeler örtüşüyor)"
        )

    return {
        "match_id": match.id,
        "product_id": match.product_id,
        "sku": prod.sku if prod else "-",
        "urun_adi": prod.urun_adi if prod else "Bilinmeyen Ürün",
        "benim_fiyatim": prod.fiyat if prod else 0.0,
        "competitor_id": match.competitor_id,
        "rakip_adi": comp.ad if comp else f"Rakip #{match.competitor_id}",
        "ham_urun_adi": match.ham_urun_adi,
        "rakip_fiyat": latest_snap.fiyat if latest_snap else None,
        "skor": match.skor,
        "durum": match.durum,
        "oneri_metni": oneri_metni,
    }


@app.get("/eslesmeler", response_class=HTMLResponse, tags=["Web Paneli"])
def get_matches_review_page(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    """
    Kılavuz Gün 3 (17:00-18:30 Eşleşme onay ekranı):
    Durumu 'onay_bekliyor' olan eşleşmeleri iki ürün adı yan yana gösterilen
    bir listede 'Aynı ürün' ve 'Farklı ürün' butonlarıyla sunar.
    """
    products_by_id = {p.id: p for p in db.query(Product).all()}
    competitors_by_id = {c.id: c for c in db.query(Competitor).all()}

    pending_rows = (
        db.query(Match)
        .filter(Match.durum == "onay_bekliyor")
        .order_by(desc(Match.skor), Match.id.asc())
        .all()
    )
    decided_rows = (
        db.query(Match)
        .filter(Match.durum.in_(["onayli", "reddedildi"]))
        .order_by(desc(Match.id))
        .all()
    )

    bekleyenler = [
        _serialize_match_row(db, m, products_by_id, competitors_by_id)
        for m in pending_rows
    ]
    tamamlananlar = [
        _serialize_match_row(db, m, products_by_id, competitors_by_id)
        for m in decided_rows
    ]

    return templates.TemplateResponse(
        request=request,
        name="matches.html",
        context={
            "bekleyenler": bekleyenler,
            "tamamlananlar": tamamlananlar,
        },
    )


@app.post("/eslesmeler/{match_id}/karar", tags=["Web Paneli"])
async def post_match_decision(
    match_id: int, request: Request, db: Session = Depends(get_db)
):
    """
    Kılavuz Gün 3 (17:00-18:30 Eşleşme onay ekranı):
    'Aynı ürün' (onayli) veya 'Farklı ürün' (reddedildi) butonuna basıldığında
    matches tablosunda durumu günceller.
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(
            status_code=404, detail=f"ID={match_id} olan eşleşme bulunamadı."
        )

    raw_body = (await request.body()).decode("utf-8", errors="replace").strip()
    karar_val = ""
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type and raw_body:
        try:
            body_json = json.loads(raw_body)
            karar_val = str(body_json.get("karar", "")).strip().lower()
        except Exception:
            karar_val = ""
    else:
        parsed_form = parse_qs(raw_body)
        karar_val = parsed_form.get("karar", [""])[0].strip().lower()

    if karar_val in ("onayli", "ayni", "same", "approve"):
        match.durum = "onayli"
    elif karar_val in ("reddedildi", "farkli", "different", "reject"):
        match.durum = "reddedildi"
    else:
        raise HTTPException(
            status_code=400,
            detail="Geçersiz karar değeri. 'onayli' veya 'reddedildi' olmalıdır.",
        )

    db.commit()

    # Onaylanan eşleşmenin 14 günlük örnek geçmişini de tamamla
    if match.durum == "onayli":
        seed_price_history(db, days=14)

    if "application/json" in content_type:
        return {"ok": True, "match_id": match.id, "yeni_durum": match.durum}

    return RedirectResponse(url="/eslesmeler", status_code=303)


@app.get("/api/eslesmeler", tags=["API"])
def get_api_eslesmeler(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Onay bekleyen ve manuel karar verilmiş eşleşmeleri JSON olarak döndürür."""
    products_by_id = {p.id: p for p in db.query(Product).all()}
    competitors_by_id = {c.id: c for c in db.query(Competitor).all()}

    pending_rows = (
        db.query(Match)
        .filter(Match.durum == "onay_bekliyor")
        .order_by(desc(Match.skor), Match.id.asc())
        .all()
    )
    decided_rows = (
        db.query(Match)
        .filter(Match.durum.in_(["onayli", "reddedildi"]))
        .order_by(desc(Match.id))
        .all()
    )

    return {
        "bekleyen_sayisi": len(pending_rows),
        "bekleyenler": [
            _serialize_match_row(db, m, products_by_id, competitors_by_id)
            for m in pending_rows
        ],
        "tamamlananlar": [
            _serialize_match_row(db, m, products_by_id, competitors_by_id)
            for m in decided_rows
        ],
    }


@app.get("/api/ozet", tags=["API"])
def get_ozet(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Kılavuz Gün 3 (09:00-11:00 API iskeleti):
    Toplam ürün, rakibin ucuz olduğu ürün sayısı, son güncelleme zamanı ve son raporu döndürür.
    """
    products = db.query(Product).order_by(Product.id.asc()).all()
    competitors_by_id = {c.id: c for c in db.query(Competitor).all()}
    role_map = _get_competitor_role_map(db)

    total_products = len(products)
    competitor_cheaper_count = 0

    for prod in products:
        item = _build_product_comparison_item(db, prod, competitors_by_id, role_map)
        if item["durum"] == "RAKİP UCUZ":
            competitor_cheaper_count += 1

    latest_snap = (
        db.query(PriceSnapshot)
        .order_by(desc(PriceSnapshot.cekilme_zamani), desc(PriceSnapshot.id))
        .first()
    )
    son_guncelleme = (
        latest_snap.cekilme_zamani.strftime("%Y-%m-%d %H:%M:%S")
        if latest_snap and latest_snap.cekilme_zamani
        else "Henüz veri yok"
    )

    pending_matches_count = (
        db.query(Match).filter(Match.durum == "onay_bekliyor").count()
    )

    son_rapor = get_latest_report_text(db)

    return {
        "toplam_urun": total_products,
        "rakibin_ucuz_oldugu_urun_sayisi": competitor_cheaper_count,
        "bizim_avantajli_oldugumuz_urun_sayisi": max(
            0, total_products - competitor_cheaper_count
        ),
        "onay_bekleyen_eslesme_sayisi": pending_matches_count,
        "son_guncelleme_zamani": son_guncelleme,
        "son_rapor": son_rapor,
    }


@app.get("/api/urunler", tags=["API"])
def get_urunler(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Kılavuz Gün 3 (09:00-11:00 API iskeleti):
    Tüm ürünleri ve onaylı rakip fiyatlarını karşılaştırmalı olarak döndürür.
    """
    products = db.query(Product).order_by(Product.id.asc()).all()
    competitors_by_id = {c.id: c for c in db.query(Competitor).all()}
    role_map = _get_competitor_role_map(db)

    result: List[Dict[str, Any]] = []
    for prod in products:
        result.append(
            _build_product_comparison_item(db, prod, competitors_by_id, role_map)
        )

    return result


@app.get("/api/urun/{id}/gecmis", tags=["API"])
def get_urun_gecmis(id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Kılavuz Gün 3 (09:00-11:00 API iskeleti):
    Belirtilen ürünün (id) kendi fiyat bilgilerini ve rakiplerdeki tüm fiyat geçmişini döndürür.
    """
    product = db.query(Product).filter(Product.id == id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"ID={id} olan ürün bulunamadı.")

    competitors_by_id = {c.id: c for c in db.query(Competitor).all()}
    matches = (
        db.query(Match)
        .filter(
            Match.product_id == product.id,
            Match.durum.in_(["otomatik_onayli", "onayli"]),
        )
        .all()
    )

    rakipler_gecmis: List[Dict[str, Any]] = []
    tum_gecmis_kayitlari: List[Dict[str, Any]] = []

    for match in matches:
        comp = competitors_by_id.get(match.competitor_id)
        comp_name = comp.ad if comp else f"Rakip #{match.competitor_id}"

        snapshots = (
            db.query(PriceSnapshot)
            .filter(
                PriceSnapshot.competitor_id == match.competitor_id,
                PriceSnapshot.ham_urun_adi == match.ham_urun_adi,
            )
            .order_by(PriceSnapshot.cekilme_zamani.asc(), PriceSnapshot.id.asc())
            .all()
        )

        kayitlar = []
        for snap in snapshots:
            tarih_str = (
                snap.cekilme_zamani.strftime("%Y-%m-%d %H:%M:%S")
                if snap.cekilme_zamani
                else None
            )
            kayit_item = {
                "snapshot_id": snap.id,
                "fiyat": snap.fiyat,
                "stokta": snap.stokta,
                "cekilme_zamani": tarih_str,
                "url": snap.url,
            }
            kayitlar.append(kayit_item)
            tum_gecmis_kayitlari.append({
                "snapshot_id": snap.id,
                "competitor_id": match.competitor_id,
                "rakip_adi": comp_name,
                "ham_urun_adi": match.ham_urun_adi,
                "fiyat": snap.fiyat,
                "stokta": snap.stokta,
                "cekilme_zamani": tarih_str,
            })

        rakipler_gecmis.append({
            "competitor_id": match.competitor_id,
            "rakip_adi": comp_name,
            "ham_urun_adi": match.ham_urun_adi,
            "eslesme_skoru": match.skor,
            "eslesme_durumu": match.durum,
            "kayitlar": kayitlar,
        })

    tum_gecmis_kayitlari.sort(key=lambda x: (x.get("cekilme_zamani") or "", x.get("snapshot_id") or 0))

    min_allowed_price = round(
        product.maliyet * (1.0 + product.min_marj_yuzde / 100.0), 2
    )

    return {
        "urun": {
            "id": product.id,
            "sku": product.sku,
            "urun_adi": product.urun_adi,
            "benim_fiyatim": product.fiyat,
            "maliyet": product.maliyet,
            "min_marj_yuzde": product.min_marj_yuzde,
            "min_kabul_edilebilir_fiyat": min_allowed_price,
        },
        "rakipler": rakipler_gecmis,
        "gecmis": tum_gecmis_kayitlari,
    }

