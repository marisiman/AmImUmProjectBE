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


class RollbackOnlyDB:
    def rollback(self):
        pass


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
    stale_address_row = SimpleNamespace(
        id=1,
        name="Bu Rus",
        phone="+6285296708577",
        address="Juwana, Pati",
        city="DEMAK",
        city_id=106,
        state="JAWA TENGAH",
        country="Indonesia",
        zip_code=59517,
        created_at=datetime(2026, 1, 1),
    )
    owner_identity = SimpleNamespace(
        fullname="Toko Herbal Amimum",
        firstname=None,
        lastname=None,
        phone="+6285296708577",
        address="Ds. Bakaran Kulon RT02/Rw01, Bakaran",
    )
    monkeypatch.setattr(
        accessible_address_module,
        "get_shipment_address",
        lambda db, user_id: stale_address_row,
    )
    monkeypatch.setattr(
        accessible_address_module,
        "get_user",
        lambda db, user_id: owner_identity,
    )

    result = accessible_address_module.accessible_address(
        db=RollbackOnlyDB(),
        user_id="customer-1",
        target_user_id=accessible_address_module.OWNER_SHOP_ID,
    )

    assert result.error is None
    response = result.unwrap()
    assert response.data.name == "Toko Herbal Amimum"
    assert response.data.phone == "+6285296708577"
    assert response.data.address == "Ds. Bakaran Kulon RT02/Rw01, Bakaran"
    assert response.data.city == "DEMAK"
    assert response.data.city_id == 106
