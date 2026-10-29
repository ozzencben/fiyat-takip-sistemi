import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fiyat_takip_sistemi.core.notify import get_telegram_chat_id, send_telegram_message

if __name__ == "__main__":
    chat_id = get_telegram_chat_id()
    if chat_id:
        send_telegram_message(
            "🔔 Fiyat Takip Sistemi: Telegram bot entegrasyon testi başarılı!",
            chat_id=chat_id,
        )

