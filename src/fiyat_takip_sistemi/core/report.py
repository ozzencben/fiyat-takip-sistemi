import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from sqlalchemy.orm import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .db import SessionLocal
from .models import Competitor, Match, PriceSnapshot, Product
from .rules import Alert, Severity, evaluate_rules

# Ortam değişkenlerini yükle (.env dosyasından)
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:latest").strip()

# Gemini modelleri (öncelik sırasıyla denenecek modeller)
GEMINI_MODELS = [
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
]


def prepare_report_data(db: Session) -> Dict[str, Any]:
    """
    Kılavuz gereksinimi:
    Rakamları kesin olarak kodla hesaplar ve LLM'e verilecek yapılandırılmış JSON verisini üretir.
    - Toplam ürün sayısı
    - Rakibin ucuz olduğu ürün sayısı
    - En kritik 5 uyarı
    """
    products = db.query(Product).all()
    total_products = len(products)

    # Kural motorundan tüm uyarıları al
    all_alerts = evaluate_rules(db)

    # Rakiplerin daha ucuz olduğu benzersiz ürünlerin sayısı
    cheaper_skus = {
        a.product_sku for a in all_alerts if a.rule_type.value == "RAKIP_UCUZ"
    }
    competitor_cheaper_count = len(cheaper_skus)

    # En kritik 5 uyarıyı seç (Önce YÜKSEK, yetmezse ORTA)
    top_5_alerts: List[Alert] = []
    high_alerts = [a for a in all_alerts if a.severity == Severity.YUKSEK]
    top_5_alerts.extend(high_alerts[:5])

    if len(top_5_alerts) < 5:
        med_alerts = [a for a in all_alerts if a.severity == Severity.ORTA]
        top_5_alerts.extend(med_alerts[: (5 - len(top_5_alerts))])

    critical_alerts_data = []
    for alert in top_5_alerts:
        critical_alerts_data.append({
            "urun": alert.product_name,
            "sku": alert.product_sku,
            "rakip": alert.competitor_name,
            "bizim_fiyat": alert.current_my_price,
            "rakip_fiyat": alert.current_comp_price,
            "uyari_tipi": alert.rule_type.value,
            "oncelik": alert.severity.value,
            "durum": alert.message,
            "oneri": alert.recommendation,
        })

    report_payload = {
        "rapor_tarihi": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "toplam_urun_sayisi": total_products,
        "rakibin_ucuz_oldugu_urun_sayisi": competitor_cheaper_count,
        "bizim_daha_ucuz_oldugumuz_urun_sayisi": max(0, total_products - competitor_cheaper_count),
        "en_kritik_uyarilar": critical_alerts_data,
    }

    return report_payload


def generate_fallback_report(data: Dict[str, Any]) -> str:
    """
    Kılavuz gereksinimi:
    LLM servisine ulaşılamazsa veya kota dolarsa sistemin çökmesini engelleyen
    kural tabanlı yedek şablon rapor üretici.
    """
    total = data["toplam_urun_sayisi"]
    cheaper = data["rakibin_ucuz_oldugu_urun_sayisi"]
    advantage = data["bizim_daha_ucuz_oldugumuz_urun_sayisi"]
    alerts = data.get("en_kritik_uyarilar", [])

    lines = [
        f"📋 GÜNLÜK FİYAT VE REKABET YÖNETİCİ ÖZETİ (Kural Tabanlı Şablon Rapor - {data['rapor_tarihi']})",
        f"Kataloğumuzdaki toplam {total} üründen {cheaper} tanesinde rakiplerimizin bizden daha ucuz olduğu, "
        f"{advantage} üründe ise fiyat avantajımızı koruduğumuz tespit edilmiştir.",
        "\nÖne Çıkan Kritik Riskler ve Fırsatlar:"
    ]

    for idx, a in enumerate(alerts[:3], 1):
        lines.append(
            f"{idx}. {a['urun']} ({a['rakip']}): Rakip fiyatı {a['rakip_fiyat']:.2f} TL, "
            f"bizim fiyatımız {a['bizim_fiyat']:.2f} TL. [{a['oneri']}]"
        )

    lines.append("\nÖnerilen Aksiyonlar:")
    lines.append("1. Rakipte fiyatı sert düşen ürünlerin marj sınırları kontrol edilerek yeni fiyatlar belirlenmelidir.")
    lines.append("2. Rakiplerin stok avantajı olmayan ürünlerde kar marjı korunmalı veya artırılmalıdır.")
    lines.append("3. Marjı kurtarmayan ürünlerde fiyat kırmak yerine katma değerli teklifler düşünülmelidir.")

    return "\n".join(lines)


def _call_gemini(data: Dict[str, Any], system_prompt: str, user_content: str, key: str) -> Optional[str]:
    """Gemini API çağrısı yapar."""
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_content}"}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600},
    }

    for model_name in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
        try:
            resp = httpx.post(url, json=payload, timeout=20.0)
            if resp.status_code == 200:
                result_json = resp.json()
                candidates = result_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"].strip()
            print(f"⚠️ Gemini ({model_name}) HTTP {resp.status_code} döndü.")
        except Exception as e:
            print(f"⚠️ Gemini ({model_name}) bağlantı uyarısı: {e}")

    return None


def suggest_match_with_llm(our_product_name: str, competitor_product_name: str, score: float = 0.0) -> str:
    """
    Kılavuz Gün 2 (11:00-13:30 İsteğe bağlı):
    'onay bekliyor' eşleşmeler için LLM'e 'Bu iki ürün aynı mı?' diye sorar.
    Cevabı otomatik onay olarak değil, panelde öneri olarak göstermek üzere döndürür.
    """
    system_prompt = (
        "Sen bir e-ticaret katalog uzmanısın. Sana verilen iki ürün adının aynı ürünü "
        "temsil edip etmediğini tek bir kısa Türkçe cümleyle değerlendir. "
        "Yanıtına 'Öneri: Aynı ürün' veya 'Öneri: Farklı ürün' diyerek başla."
    )
    user_content = (
        f"Bizim ürünümüz: '{our_product_name}'\n"
        f"Rakip ürünü: '{competitor_product_name}'\n"
        f"Bu iki ürün aynı mı?"
    )

    if GEMINI_API_KEY:
        res = _call_gemini({}, system_prompt, user_content, GEMINI_API_KEY)
        if res:
            return res

    # Kural tabanlı yedek öneri
    if score >= 80.0:
        return f"Öneri: Aynı ürün (Benzerlik skoru %{score:.0f} oldukça yüksek, alt başlık/çeviri farkı olabilir)."
    return f"Öneri: İnsan kontrolü gerekli (Benzerlik skoru %{score:.0f}, ortak kelimeler mevcut)."


def _call_groq(data: Dict[str, Any], system_prompt: str, user_content: str, key: str) -> Optional[str]:
    """Groq API çağrısı yapar (Alternatif Hızlı LLM)."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "max_tokens": 600,
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=15.0)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        print(f"⚠️ Groq HTTP {resp.status_code} döndü.")
    except Exception as e:
        print(f"⚠️ Groq bağlantı uyarısı: {e}")
    return None


def generate_llm_report(data: Dict[str, Any], api_key: Optional[str] = None) -> str:
    """
    Kılavuz gereksinimi:
    Verilen yapılandırılmış JSON verisini LLM'e aktararak 5-8 cümlelik,
    asla rakam uydurmayan, aksiyon odaklı Türkçe bir yönetici özeti üretir.
    Gemini -> Groq -> Şablon Rapor hiyerarşisiyle çalışır.
    """
    system_prompt = (
        "Sen deneyimli bir e-ticaret fiyatlandırma ve rekabet stratejisi analistisin.\n"
        "Görevin, sana JSON formatında verilen günlük fiyat takip verilerini inceleyip "
        "şirket yöneticisi için kısa, net ve aksiyon odaklı bir Türkçe sabah brifingi hazırlamaktır.\n\n"
        "KESİN KURALLAR:\n"
        "1. Yalnızca Türkçe yaz.\n"
        "2. Raporun gövdesi TAM OLARAK 5 ila 8 cümle arasında olmalı, asla gereksiz uzatma.\n"
        "3. SADECE verilen JSON verilerini kullan. KESİNLİKLE RAKAM, ÜRÜN VEYA YÜZDE UYDURMA (Halüsinasyon yok).\n"
        "4. Raporun sonunda 'Aksiyon Önerileri:' başlığı altında 2 veya 3 adet net, somut aksiyon maddesi listele.\n"
        "5. Rapor profesyonel, akıcı ve yönetim kuruluna sunulabilecek kalitede olsun."
    )

    user_content = (
        f"Aşağıdaki günlük fiyat ve rekabet takip verilerini analiz ederek brifingi oluştur:\n\n"
        f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"
    )

    # 1. Öncelik: Gemini API
    gemini_key = api_key or GEMINI_API_KEY
    if gemini_key:
        print("🤖 Gemini Yapay Zeka Raporu Üretiliyor...")
        res = _call_gemini(data, system_prompt, user_content, gemini_key)
        if res:
            return res

    # 2. Öncelik: Groq API (Varsa)
    if GROQ_API_KEY:
        print("⚡ Groq API üzerinden LLM Raporu Üretiliyor...")
        res = _call_groq(data, system_prompt, user_content, GROQ_API_KEY)
        if res:
            return res

    # 3. Kılavuz kuralı: Kural Tabanlı Güvenli Şablon Rapor
    print("📋 Kılavuz kuralı gereği kural tabanlı şablon rapora geçiliyor...")
    return generate_fallback_report(data)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LAST_REPORT_FILE = PROJECT_ROOT / "data" / "last_report.json"


def save_last_report(report_text: str, report_data: Dict[str, Any]) -> None:
    """Üretilen son raporu web panelinde (/api/ozet) hızlı göstermek üzere kaydeder."""
    try:
        LAST_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "rapor_tarihi": report_data.get("rapor_tarihi", datetime.now().strftime("%Y-%m-%d %H:%M")),
            "toplam_urun_sayisi": report_data.get("toplam_urun_sayisi", 0),
            "rakibin_ucuz_oldugu_urun_sayisi": report_data.get("rakibin_ucuz_oldugu_urun_sayisi", 0),
            "son_rapor": report_text,
        }
        with open(LAST_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Son rapor dosyaya kaydedilemedi: {e}")


def get_latest_report_text(db: Session) -> str:
    """
    Varsa kaydedilmiş son raporu döndürür; yoksa güncel verilerle şablon/LLM raporu üretip kaydeder.
    Veritabanında henüz ürün veya fiyat kaydı yoksa 'Henüz veri yok' döndürür.
    """
    total_products = db.query(Product).count()
    total_snapshots = db.query(PriceSnapshot).count()
    if total_products == 0 or total_snapshots == 0:
        return "Henüz veri yok"

    report_data = prepare_report_data(db)
    if LAST_REPORT_FILE.exists():
        try:
            with open(LAST_REPORT_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if (
                cached.get("son_rapor")
                and cached.get("toplam_urun_sayisi") == report_data["toplam_urun_sayisi"]
                and cached.get("rakibin_ucuz_oldugu_urun_sayisi")
                == report_data["rakibin_ucuz_oldugu_urun_sayisi"]
            ):
                return str(cached["son_rapor"])
        except Exception:
            pass

    report_text = generate_llm_report(report_data)
    save_last_report(report_text, report_data)
    return report_text


def run_daily_report(db: Session) -> str:
    """
    Rapor akışını baştan sona çalıştırır ve üretilen raporu terminalde gösterir.
    """
    print("\n" + "=" * 80)
    print("📝 [LLM GÜNLÜK YÖNETİCİ ÖZETİ] Veriler Hazırlanıyor...")
    print("=" * 80)

    report_data = prepare_report_data(db)
    print(f"✓ Kodla hesaplanan veriler:")
    print(f"  • Toplam Ürün Sayısı        : {report_data['toplam_urun_sayisi']}")
    print(f"  • Rakibin Ucuz Olduğu Ürün  : {report_data['rakibin_ucuz_oldugu_urun_sayisi']}")
    print(f"  • Bizim Avantajlı Olduğumuz : {report_data['bizim_daha_ucuz_oldugumuz_urun_sayisi']}")
    print(f"  • İncelenen Kritik Uyarı    : {len(report_data['en_kritik_uyarilar'])} adet")

    report_text = generate_llm_report(report_data)
    save_last_report(report_text, report_data)

    print("\n" + "=" * 80)
    print("📌 GÜNLÜK SABAH RAPORU (EXECUTIVE SUMMARY)")
    print("=" * 80)
    print(report_text)
    print("=" * 80 + "\n")

    return report_text


if __name__ == "__main__":
    session = SessionLocal()
    try:
        run_daily_report(session)
    finally:
        session.close()
