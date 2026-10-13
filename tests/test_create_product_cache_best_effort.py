import importlib
from datetime import datetime, timezone

from app.dtos.product_dtos import ProductCreateDTO


class FakeDb:
    def __init__(self):
        self.added = None
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        obj.id = "product-123"
        obj.is_active = True
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

    def rollback(self):
        self.rolled_back = True


def test_create_product_succeeds_when_cache_invalidation_fails(monkeypatch):
    module = importlib.import_module("app.services.product_services.create_product")
    cache_utils = importlib.import_module("app.services.product_services.cache_utils")

    class FailingRedis:
        def scan_iter(self, _pattern):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(cache_utils, "redis_client", FailingRedis())

    payload = ProductCreateDTO(
        name="Produk Test Cache",
        info="Info test",
        weight=10,
        description="Deskripsi test",
        instruction="Instruksi test",
        price=1000,
        product_by_id=1,
    )
    db = FakeDb()

    result = module.create_product(db, payload)

    assert result.error is None
    response = result.unwrap()
    assert response.status_code == 201
    assert response.data.id == "product-123"
    assert db.committed is True
    assert db.rolled_back is False
