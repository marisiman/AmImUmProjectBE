import importlib
from datetime import datetime
from types import SimpleNamespace

from app.services.shipment_address_services import cache_utils

accessible_address_module = importlib.import_module(
    "app.services.shipment_address_services.accessible_address"
)


class FakeRedis:
    def __init__(self):
        self.deleted = []
        self.patterns = []

    def scan_iter(self, pattern):
        self.patterns.append(pattern)
        if pattern.endswith(":*"):
            yield f"{pattern[:-1]}cached-list"

    def delete(self, *keys):
        self.deleted.extend(keys)


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class FakeExecuteResult:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return FakeScalarResult(self.value)


class FakeDB:
    def __init__(self, address):
        self.address = address

    def execute(self, _statement):
        return FakeExecuteResult(self.address)


def test_invalidate_user_address_cache_deletes_owner_address_exact_key(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(cache_utils, "redis_client", fake_redis)

    cache_utils.invalidate_user_address_cache("owner-123")

    assert "origin_address:owner-123" in fake_redis.deleted
    assert "origin_address:owner-123:*" in fake_redis.patterns
    assert "origin_address:v2:owner-123:*" in fake_redis.patterns


def test_owner_accessible_address_uses_database_not_stale_cache(monkeypatch):
    class StaleRedis:
        def get(self, _key):
            raise AssertionError("owner-address should not read Redis cache")

    monkeypatch.setattr(accessible_address_module, "redis_client", StaleRedis(), raising=False)
    db = FakeDB(
        SimpleNamespace(
            id=1,
            name="Alamat Toko Baru",
            phone="+6281234567890",
            address="Alamat baru dari database",
            city="DEMAK",
            city_id=106,
            state="JAWA TENGAH",
            country="Indonesia",
            zip_code=59517,
            created_at=datetime(2026, 1, 1),
        )
    )

    result = accessible_address_module.accessible_address(
        db=db,
        user_id="customer-1",
        target_user_id=accessible_address_module.OWNER_SHOP_ID,
    )

    assert result.error is None
    response = result.unwrap()
    assert response.data.name == "Alamat Toko Baru"
    assert response.data.address == "Alamat baru dari database"
