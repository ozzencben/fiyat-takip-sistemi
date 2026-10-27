# core/models.py
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .db import Base


class Product(Base):
    """Excel'den aktarılan kendi ürünlerimiz."""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True, nullable=False)
    urun_adi = Column(String, nullable=False)
    fiyat = Column(Float, nullable=False)
    maliyet = Column(Float, nullable=False)
    min_marj_yuzde = Column(Float, nullable=False)

    matches = relationship("Match", back_populates="product")


class Competitor(Base):
    """İzlenen rakip siteler."""
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True, index=True)
    ad = Column(String, nullable=False)
    base_url = Column(String, nullable=False)

    snapshots = relationship("PriceSnapshot", back_populates="competitor")
    matches = relationship("Match", back_populates="competitor")


class PriceSnapshot(Base):
    """Rakiplerden çekilen ham zaman serisi kayıtları."""
    __tablename__ = "price_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    competitor_id = Column(Integer, ForeignKey("competitors.id"), nullable=False)
    ham_urun_adi = Column(String, index=True, nullable=False)
    url = Column(String, nullable=False)
    fiyat = Column(Float, nullable=False)
    stokta = Column(Boolean, default=True, nullable=False)
    cekilme_zamani = Column(DateTime, default=datetime.utcnow, nullable=False)

    competitor = relationship("Competitor", back_populates="snapshots")


class Match(Base):
    """Ürünlerimiz ile rakip ürünler arasındaki eşleşme köprüsü."""
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    competitor_id = Column(Integer, ForeignKey("competitors.id"), nullable=False)
    ham_urun_adi = Column(String, nullable=False)
    skor = Column(Float, nullable=False)
    durum = Column(String, default="onay_bekliyor", nullable=False)  # otomatik_onayli, onay_bekliyor, onayli, reddedildi

    product = relationship("Product", back_populates="matches")
    competitor = relationship("Competitor", back_populates="matches")