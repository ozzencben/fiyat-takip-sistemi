import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Fake Bookstore - Rakip C")

# data/prices.json yolunu dinamik bul
def get_prices_file() -> Path:
    candidates = [
        Path("data/prices.json"),
        Path(__file__).resolve().parent.parent / "data" / "prices.json",
        Path(__file__).resolve().parent / "data" / "prices.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return Path("data/prices.json")


def load_products():
    path = get_prices_file()
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/", response_class=HTMLResponse)
@app.get("/products", response_class=HTMLResponse)
def get_products_page():
    products = load_products()

    cards_html = ""
    for p in products:
        stock_text = "Stokta Var" if p.get("in_stock", True) else "Tükendi"
        stock_badge = "bg-green" if p.get("in_stock", True) else "bg-red"
        cards_html += f"""
        <article class="product-card">
            <h3 class="product-title">{p.get('name')}</h3>
            <p class="product-price">{p.get('price'):.2f} TL</p>
            <span class="product-stock {stock_badge}">{stock_text}</span>
            <div class="product-actions">
                <a href="{p.get('url', '#')}" class="product-link">Ürünü İncele</a>
            </div>
        </article>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kitap Dünyası - Rakip C Mağazası</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        body {{ background: #f8fafc; color: #1e293b; padding: 2rem; }}
        header {{ max-width: 1200px; margin: 0 auto 2rem auto; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e2e8f0; padding-bottom: 1rem; }}
        h1 {{ font-size: 1.75rem; color: #0f172a; }}
        .badge {{ background: #e0e7ff; color: #3730a3; padding: 0.35rem 0.75rem; border-radius: 9999px; font-size: 0.875rem; font-weight: 600; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1.5rem; max-width: 1200px; margin: 0 auto; }}
        .product-card {{ background: #ffffff; border-radius: 0.75rem; padding: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; display: flex; flex-direction: column; justify-content: space-between; transition: transform 0.15s ease; }}
        .product-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
        .product-title {{ font-size: 1rem; font-weight: 600; color: #1e293b; margin-bottom: 0.75rem; line-height: 1.4; min-height: 2.8rem; }}
        .product-price {{ font-size: 1.35rem; font-weight: 700; color: #059669; margin-bottom: 0.5rem; }}
        .product-stock {{ display: inline-block; font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.5rem; border-radius: 0.375rem; width: fit-content; margin-bottom: 1rem; }}
        .bg-green {{ background: #d1fae5; color: #065f46; }}
        .bg-red {{ background: #fee2e2; color: #991b1b; }}
        .product-link {{ display: block; text-align: center; background: #2563eb; color: #ffffff; text-decoration: none; padding: 0.5rem 1rem; border-radius: 0.5rem; font-size: 0.875rem; font-weight: 500; }}
        .product-link:hover {{ background: #1d4ed8; }}
    </style>
</head>
<body>
    <header>
        <div>
            <h1>Kitap Dünyası</h1>
            <p style="color: #64748b; font-size: 0.875rem;">Rakip C Simülasyon Mağazası (Port 8001)</p>
        </div>
        <span class="badge">{len(products)} Ürün Listeleniyor</span>
    </header>
    <main class="grid">
        {cards_html}
    </main>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@app.get("/products/{product_id}")
def get_product_detail(product_id: int):
    products = load_products()
    for p in products:
        if p.get("id") == product_id:
            return p
    return {"error": "Ürün bulunamadı"}


if __name__ == "__main__":
    print("🚀 Rakip C Sahte Mağazası http://localhost:8001 adresinde başlatılıyor...")
    uvicorn.run("fake_store.main:app", host="127.0.0.1", port=8001, reload=True)
