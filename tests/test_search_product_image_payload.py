from datetime import datetime, timezone
from types import SimpleNamespace
import importlib


search_product_module = importlib.import_module("app.services.product_services.search_product")


class ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class SearchDB:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return ScalarResult(self.rows)

    def rollback(self):
        pass


def test_search_product_returns_primary_and_sorted_gallery_images():
    product = SimpleNamespace(
        id="product-1",
        name="Herbal Test",
        price=10000,
        min_variant_price=9000,
        max_variant_price=12000,
        brand_info={"id": 4, "name": "Brand Test"},
        all_variants=[],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        product_images=[
            SimpleNamespace(
                id=2,
                url="https://images.example/second.webp",
                is_primary=False,
                sort_order=1,
            ),
            SimpleNamespace(
                id=1,
                url="https://images.example/primary.webp",
                is_primary=True,
                sort_order=0,
            ),
        ],
    )
    db = SearchDB([product])

    result = search_product_module.search_product(db, "Herbal")

    assert result.error is None
    searched_product = result.data.data[0]
    assert searched_product.primary_image_url == "https://images.example/primary.webp"
    assert searched_product.gallery_images == [
        {"id": 1, "url": "https://images.example/primary.webp", "is_primary": True, "sort_order": 0},
        {"id": 2, "url": "https://images.example/second.webp", "is_primary": False, "sort_order": 1},
    ]
