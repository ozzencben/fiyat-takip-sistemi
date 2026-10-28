import argparse
import sys
from datetime import datetime

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .core.logger import get_logger
from .core.notify import send_telegram_message
from .run_daily import run_daily

logger = get_logger("scheduler")

# Kılavuz gereksinimi:
# Normal çalışma: Her gün 09:00'da çalışır.
# Test modu (--test veya TEST_MODE=True): Her 1 dakikada bir çalışır.
DAILY_HOUR = 9
DAILY_MINUTE = 0
TEST_INTERVAL_MINUTES = 1


def scheduled_job_wrapper() -> None:
    """
    Zamanlayıcı tarafından tetiklenen görev sarmalayıcısı.
    Başlangıç ve bitiş zamanlarını logs/fiyat_takip.log dosyasına yazar.
    """
    logger.info(f"⏰ Zamanlanmış görev tetiklendi ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}).")
    try:
        run_daily()
        logger.info("✓ Zamanlanmış görev başarıyla tamamlandı.")
    except Exception as exc:
        error_msg = f"Zamanlanmış görev sırasında beklenmeyen hata: {exc}"
        logger.error(error_msg)
        send_telegram_message(f"⚠️ <b>Zamanlayıcı Hatası:</b> Günlük görev çalışırken hata oluştu:\n{exc}")


def start_scheduler(test_mode: bool = False, max_runs: int = 0) -> None:
    """
    APScheduler BlockingScheduler başlatır.
    - test_mode=False: Her gün saat 09:00'da çalıştırır.
    - test_mode=True : Test amacıyla her 1 dakikada bir çalıştırır.
    - max_runs > 0   : Belirtilen sayıda çalışmadan sonra zamanlayıcıyı otomatik kapatır.
    """
    scheduler = BlockingScheduler()

    if test_mode:
        trigger = IntervalTrigger(minutes=TEST_INTERVAL_MINUTES)
        schedule_desc = f"TEST MODU - Her {TEST_INTERVAL_MINUTES} dakikada bir"
    else:
        trigger = CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE)
        schedule_desc = f"GÜNLÜK MOD - Her gün saat {DAILY_HOUR:02d}:{DAILY_MINUTE:02d}'da"

    scheduler.add_job(
        scheduled_job_wrapper,
        trigger=trigger,
        id="fiyat_takip_daily_job",
        name="Günlük Fiyat Takip ve Raporlama Görevi",
        replace_existing=True,
    )

    run_counter = {"count": 0}

    def job_listener(event):
        run_counter["count"] += 1
        if event.exception:
            logger.error(f"APScheduler iş hatası (Job ID: {event.job_id}): {event.exception}")
        else:
            logger.info(f"APScheduler işi tamamlandı (Job ID: {event.job_id}).")

        if max_runs > 0 and run_counter["count"] >= max_runs:
            logger.info(f"Hedeflenen çalışma sayısına ({max_runs}) ulaşıldı, zamanlayıcı kapatılıyor.")
            scheduler.shutdown(wait=False)

    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    print("=" * 80)
    print("🕒 [ZAMANLAYICI] Fiyat Takip Sistemi APScheduler Başlatıldı")
    print(f"   • Çalışma Planı : {schedule_desc}")
    print("   • Log Dosyası   : logs/fiyat_takip.log")
    print("   • Durdurmak için: Ctrl+C")
    print("=" * 80)

    logger.info(f"Zamanlayıcı başlatıldı ({schedule_desc}).")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Zamanlayıcı kullanıcı tarafından durduruldu.")
        print("\n⏹️ Zamanlayıcı durduruldu.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fiyat Takip Sistemi Zamanlayıcısı")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test için zamanlayıcıyı her 1 dakikada bir çalışacak şekilde başlatır.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Test sırasında belirtilen çalışma sayısından sonra zamanlayıcıyı durdurur.",
    )
    args = parser.parse_args()
    start_scheduler(test_mode=args.test, max_runs=args.max_runs)
