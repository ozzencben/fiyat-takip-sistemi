from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseAdapter(ABC):
    """
    Tüm rakip site adaptörleri için temel sözleşme (Interface).
    Her adaptör fetch_products() metodunu uygulayarak standart bir ürün listesi döndürmelidir.
    """

    def __init__(self, competitor_name: str, base_url: str):
        self.competitor_name = competitor_name
        self.base_url = base_url

    @abstractmethod
    def fetch_products(self) -> List[Dict[str, Any]]:
        """
        Rakip siteden ürünleri çeker ve standart formatta bir liste döndürür.
        Her eleman şu anahtarları içermelidir:
            - name (str): Ürünün ham adı
            - price (float): Ürünün fiyatı (TL cinsinden)
            - in_stock (bool): Stokta olup olmadığı
            - url (str): Ürünün doğrudan tam URL adresi
        """
        pass
