import json
import random
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def get_prices_file() -> Path:
    candidates = [
        Path("data/prices.json"),
        Path(__file__).resolve().parent.parent / "data" / "prices.json",
        Path(__file__).resolve().parents[2] / "data" / "prices.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return Path("data/prices.json")


def simulate_price_drop(num_products: int = 5) -> None:
    prices_file = get_prices_file()
    if not prices_file.exists():
        print(f"Hata: {prices_file} bulunamadı!")
        return

    with open(prices_file, "r", encoding="utf-8") as f:
        products = json.load(f)

    if not products:
        print("Hata: Ürün listesi boş!")
        return

    # Rastgele 5 veya 6 ürün seç
    sample_size = min(num_products, len(products))
    chosen_products = random.sample(products, sample_size)

    print(f"\n📉 [Fiyat Değişimi Simülasyonu] {sample_size} üründe indirim uygulanıyor:")
    print("-" * 65)

    for prod in chosen_products:
        old_price = prod["price"]
        # %5 ile %15 arasında rastgele indirim
        drop_pct = random.uniform(5.0, 15.0)
        new_price = round(old_price * (1.0 - drop_pct / 100.0), 2)
        prod["price"] = new_price

        print(
            f"• {prod['name'][:35]:<35} | {old_price:.2f} TL -> {new_price:.2f} TL (-%{drop_pct:.1f})"
        )

    with open(prices_file, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print("-" * 65)
    print(f"✓ {prices_file} başarıyla güncellendi!\n")


if __name__ == "__main__":
    count = random.choice([5, 6])
    simulate_price_drop(count)
