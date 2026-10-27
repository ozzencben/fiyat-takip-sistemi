# Fiyat Takip Sistemi (E-Ticaret Rakip Fiyat İzleme Demosu)

E-ticaret siteleri için rakiplerin fiyat hareketlerini izleyen, kural motoruyla marj ve rekabet analizleri yapan, anlık uyarı ve rapor üreten uçtan uca fiyat takip sistemi.

## 📌 Proje Mimarisi ve Veri Akışı
Sistem modüler ve genişletilebilir bir yapıda tasarlanmıştır:
- **`data/`**: Kendi ürün kataloğumuz (`urunlerim.xlsx`) ve sahte mağaza verileri (`prices.json`).
- **`src/fiyat_takip_sistemi/core/`**: SQLAlchemy veri modelleri, veritabanı yönetimi ve Excel aktarımı.
- **`src/fiyat_takip_sistemi/adapters/`**: "Her siteye tek bir adaptör" prensibiyle çalışan web kazıma adaptörleri (`BaseAdapter` miraslı).
- **`fake_store/`**: Kontrollü fiyat değişimi senaryolarını test etmek için geliştirilmiş bağımsız FastAPI sahte mağazası.
- **`scripts/`**: Fiyat değişimi simülasyonu ve yardımcı araçlar.

---

## 💱 Kur Bilgisi ve Sabit Çarpan
Rakip A (`books.toscrape.com`) üzerindeki fiyatlar İngiliz Sterlini (£) cinsindendir. Demo ortamında TL bazlı ürünlerimizle tutarlı ve anlamlı bir karşılaştırma yapabilmek için **sabit kur çarpanı** belirlenmiştir:

> **1 £ = 40.0 TL**  
> Kod içerisinde `KUR_GBP_TL = 40.0` sabiti ile merkezi olarak yönetilmektedir.

---

## 🚀 Kurulum ve Çalıştırma

### 1. Gereksinimler
- Python 3.11+
- `uv` (veya `pip`)

### 2. Bağımlılıkların Kurulması
```bash
uv sync
# veya
pip install -r requirements.txt
```

### 3. Veritabanının Başlatılması ve Excel Verilerinin Yüklenmesi
```bash
# Tabloları ve varsayılan rakipleri oluştur
uv run python -m fiyat_takip_sistemi.core.init_db

# Kendi ürünlerimizi (25 kitap) veritabanına aktar
uv run python -m fiyat_takip_sistemi.core.load_excel
```

### 4. Rakip Adaptörlerinin Çalıştırılması

#### Rakip A (BooksToScrape)
```bash
uv run python -m fiyat_takip_sistemi.adapters.books_toscrape
```

#### Rakip C (Sahte Mağaza)
```bash
# 1. Terminal: Sahte mağazayı başlat (Port 8001)
uv run uvicorn fake_store.main:app --port 8001

# 2. Terminal: Sahte mağaza adaptörünü koştur
uv run python -m fiyat_takip_sistemi.adapters.fake_store

# 3. İsteğe bağlı: Fiyat değişimi simülasyonu
uv run python -m fiyat_takip_sistemi.scripts.simulate_price_change
```

---

## 📊 Veritabanı Tabloları
- `products`: Kendi ürünlerimiz (`sku`, `urun_adi`, `fiyat`, `maliyet`, `min_marj_yuzde`).
- `competitors`: İzlenen rakipler (`Rakip A` ve `Rakip C`).
- `price_snapshots`: Rakiplerden çekilen ham fiyat ve stok zaman serisi kayıtları.
- `matches`: Kendi ürünlerimiz ile rakip ürünler arasındaki eşleşme köprüsü.
