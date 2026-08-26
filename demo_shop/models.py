"""Baseline ("before") state for the live demo PR. See demo_shop/README.md."""

from dataclasses import dataclass


@dataclass
class Category:
    name: str


@dataclass
class DiscountCode:
    code: str
    percent_off: float


@dataclass
class Product:
    name: str
    price: float
    category: Category

    def apply_discount(self, percent: float, code: DiscountCode | None) -> float:
        return self.price * (1 - percent / 100)


class Cart:
    def __init__(self):
        self.items: list[Product] = []
        self.discount_code: DiscountCode | None = None

    def add(self, product: Product) -> None:
        self.items.append(product)

    def apply_code(self, code: DiscountCode) -> None:
        self.discount_code = code

    def total(self) -> float:
        return sum(p.price for p in self.items)
