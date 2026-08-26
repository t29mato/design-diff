"""Baseline ("before") state for the live demo PR. See demo_shop/README.md."""

from dataclasses import dataclass


@dataclass
class Category:
    name: str


@dataclass
class Product:
    name: str
    price: float
    category: Category

    def apply_discount(self, percent: float) -> float:
        return self.price * (1 - percent / 100)


@dataclass
class LegacyCouponBanner:
    text: str


class Cart:
    def __init__(self):
        self.items: list[Product] = []
        self.legacy_notes: str = ""

    def add(self, product: Product) -> None:
        self.items.append(product)

    def send_legacy_receipt(self) -> None:
        pass

    def total(self) -> float:
        return sum(p.price for p in self.items)
