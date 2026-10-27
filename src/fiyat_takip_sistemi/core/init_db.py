import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .db import Base, SessionLocal, engine
from .models import Competitor


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Varsayılan 2 rakibi ekle (yoksa)
        mevcut_rakipler = {c.ad for c in db.query(Competitor).all()}
        
        varsayilanlar = [
            Competitor(ad="Rakip A (BooksToScrape)", base_url="https://books.toscrape.com"),
            Competitor(ad="Rakip C (Sahte Magaza)", base_url="http://localhost:8001"),
        ]
        
        for rakip in varsayilanlar:
            if rakip.ad not in mevcut_rakipler:
                db.add(rakip)
        
        db.commit()
        print("✓ Tablolar ve varsayılan rakipler başarıyla oluşturuldu.")
    finally:
        db.close()


if __name__ == "__main__":
    init_database()