import os
import sys
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ortam değişkenlerini yükle
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

MAX_TELEGRAM_MESSAGE_LENGTH = 4096


def get_telegram_chat_id(token: Optional[str] = None) -> Optional[str]:
    """
    Kullanıcının bota attığı son mesajdan chat_id değerini otomatik tespit eder.
    """
    bot_token = token or TELEGRAM_TOKEN
    if not bot_token:
        print("⚠️ TELEGRAM_TOKEN tanımlı değil.")
        return None

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        resp = httpx.get(url, timeout=30.0)
        if resp.status_code == 200:
            updates = resp.json().get("result", [])
            if updates:
                last_update = updates[-1]
                chat = (
                    last_update.get("message", {}).get("chat", {})
                    or last_update.get("edited_message", {}).get("chat", {})
                    or last_update.get("channel_post", {}).get("chat", {})
                )
                chat_id = chat.get("id")
                if chat_id:
                    return str(chat_id)
        else:
            print(f"⚠️ getUpdates başarısız (HTTP {resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"⚠️ Telegram getUpdates hatası: {e}")

    return None


def format_daily_notification_message(
    llm_report: str, critical_alerts: List[Dict[str, Any]]
) -> str:
    """
    Kılavuz gereksinimi:
    Mesaj formatı: LLM raporu + en kritik 3 uyarı.
    Telegram mesajı 4096 karakteri geçemez, uzunsa kısalt.
    """
    sections = [
        "📊 <b>GÜNLÜK FİYAT TAKİP VE REKABET BRİFİNGİ</b>",
        "──────────────────────────────",
        llm_report.strip(),
        "\n🚨 <b>ÖNE ÇIKAN KRİTİK UYARILAR (İLK 3)</b>",
        "──────────────────────────────",
    ]

    for idx, alert in enumerate(critical_alerts[:3], 1):
        urun = alert.get("urun", "Bilinmeyen Ürün")
        rakip = alert.get("rakip", "Rakip")
        bizim_fiyat = alert.get("bizim_fiyat", 0.0)
        rakip_fiyat = alert.get("rakip_fiyat", 0.0)
        oneri = alert.get("oneri", "Aksiyon önerisi yok")
        durum = alert.get("durum", "")

        sections.append(
            f"<b>{idx}. {urun}</b>\n"
            f"   • Rakip: {rakip}\n"
            f"   • Bizim: {bizim_fiyat:.2f} TL | Rakip: {rakip_fiyat:.2f} TL\n"
            f"   • Durum: {durum}\n"
            f"   • 💡 <i>{oneri}</i>\n"
        )

    full_message = "\n".join(sections)

    # 4096 karakter sınır kontrolü
    if len(full_message) > MAX_TELEGRAM_MESSAGE_LENGTH:
        full_message = (
            full_message[: MAX_TELEGRAM_MESSAGE_LENGTH - 40]
            + "\n\n... [Mesaj sınırı aşıldığı için kısaltıldı]"
        )

    return full_message


def send_telegram_message(
    text: str,
    chat_id: Optional[str] = None,
    token: Optional[str] = None,
    parse_mode: str = "HTML",
) -> bool:
    """
    Kılavuz gereksinimi:
    httpx ile Telegram'ın sendMessage metodunu çağıran fonksiyon.
    """
    bot_token = token or TELEGRAM_TOKEN
    target_chat_id = chat_id or TELEGRAM_CHAT_ID

    if not bot_token:
        print("❌ Hata: TELEGRAM_TOKEN .env dosyasında bulunamadı!")
        return False

    if not target_chat_id:
        print("⚠️ TELEGRAM_CHAT_ID bulunamadı, getUpdates ile otomatik aranıyor...")
        target_chat_id = get_telegram_chat_id(bot_token)
        if target_chat_id:
            print(f"✓ Chat ID otomatik tespit edildi: {target_chat_id}")
        else:
            print("❌ Hata: TELEGRAM_CHAT_ID tespit edilemedi.")
            print("   Lütfen Telegram'da @FaturaTakipSistemiBot botunuza gidip /start veya bir mesaj yazın!")
            return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        resp = httpx.post(url, json=payload, timeout=30.0)
        if resp.status_code == 200:
            print(f"✓ Telegram bildirimi başarıyla gönderildi! (Chat ID: {target_chat_id})")
            return True
        else:
            print(f"❌ Telegram gönderimi başarısız (HTTP {resp.status_code}): {resp.text}")
            # HTML formatlama hatası ihtimaline karşı düz metin olarak tekrar dene
            if parse_mode == "HTML":
                payload["parse_mode"] = ""
                retry_resp = httpx.post(url, json=payload, timeout=30.0)
                if retry_resp.status_code == 200:
                    print("✓ Düz metin formatında başarıyla iletildi.")
                    return True
            return False
    except Exception as e:
        print(f"❌ Telegram bağlantı hatası: {e}")
        return False


if __name__ == "__main__":
    print("🤖 Telegram Bildirim Testi Başlatılıyor...")
    load_dotenv()
    chat_id = get_telegram_chat_id()
    if chat_id:
        print(f"✓ Aktif Chat ID bulundu: {chat_id}")
        send_telegram_message("🔔 Fiyat Takip Sistemi: Telegram bot entegrasyon testi başarılı!", chat_id=chat_id)
    else:
        print("⚠️ Henüz bota bir mesaj atılmamış.")
        print("   Lütfen Telegram uygulamasından @FaturaTakipSistemiBot botunu açın ve /start yazın.")
