from types import SimpleNamespace


class _FakeScalarsWithRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeExecuteRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalarsWithRows(self._rows)


class _FakeCleanupDB:
    def __init__(self, rows):
        self.rows = rows
        self.deleted = []
        self.committed = False

    def execute(self, stmt):
        return _FakeExecuteRowsResult(self.rows)

    def delete(self, row):
        self.deleted.append(row)

    def commit(self):
        self.committed = True


def test_my_cart_cleanup_deletes_stale_inactive_checked_out_rows(monkeypatch):
    import importlib

    my_cart_module = importlib.import_module("app.services.cart_services.my_cart")
    stale_inactive_row = SimpleNamespace(id=396, is_active=False)
    db = _FakeCleanupDB([stale_inactive_row])

    monkeypatch.setattr(my_cart_module, "redis_client", None)

    deleted_count = my_cart_module._delete_stale_checked_out_cart_rows(db, "user-1")

    assert deleted_count == 1
    assert db.deleted == [stale_inactive_row]
    assert db.committed is True



def test_my_cart_lists_all_cart_rows_because_is_active_is_checkout_selection(monkeypatch):
    import importlib

    my_cart_module = importlib.import_module("app.services.cart_services.my_cart")

    where_args = []

    class ColumnProbe:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return (self.name, other)

    class FakeSelect:
        def where(self, *args):
            where_args.extend(args)
            return self

        def offset(self, value):
            return self

        def limit(self, value):
            return self

    class FakeScalars:
        def all(self):
            return []

    class FakeExecuteResult:
        def scalars(self):
            return FakeScalars()

    class FakeDB:
        def execute(self, stmt):
            return FakeExecuteResult()

    monkeypatch.setattr(my_cart_module, "redis_client", None)
    monkeypatch.setattr(my_cart_module, "_delete_stale_checked_out_cart_rows", lambda db, user_id: 0)
    monkeypatch.setattr(
        my_cart_module,
        "CartProductModel",
        SimpleNamespace(
            customer_id=ColumnProbe("customer_id"),
            is_active=ColumnProbe("is_active"),
        ),
    )
    monkeypatch.setattr(my_cart_module, "select", lambda model: FakeSelect())

    result = my_cart_module.my_cart(FakeDB(), "user-1")

    assert result.error is None
    assert ("customer_id", "user-1") in where_args
    assert ("is_active", True) not in where_args
    assert result.data.data == []


def test_my_cart_returns_product_and_variant_ids_with_versioned_cache(monkeypatch):
    import importlib
    from datetime import datetime, timezone

    from app.dtos.cart_dtos import CartProductTotalDto

    my_cart_module = importlib.import_module("app.services.cart_services.my_cart")
    cart_row = SimpleNamespace(
        id=83,
        product_id="product-83",
        variant_id=31,
        product_name="Jahe Merah",
        product_price=30000,
        variant_info={"id": 31, "variant": "250 gram"},
        quantity=3,
        is_active=True,
        created_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        total_price_no_discount=90000,
        total_promo=0,
    )

    class ColumnProbe:
        def __eq__(self, other):
            return True

    class FakeSelect:
        def where(self, *args):
            return self

        def offset(self, value):
            return self

        def limit(self, value):
            return self

    class FakeScalars:
        def all(self):
            return [cart_row]

    class FakeExecuteResult:
        def scalars(self):
            return FakeScalars()

    class FakeDB:
        def execute(self, stmt):
            return FakeExecuteResult()

    class FakeRedis:
        def __init__(self):
            self.read_keys = []

        def get(self, key):
            self.read_keys.append(key)
            return None

        def setex(self, key, ttl, value):
            return None

    fake_redis = FakeRedis()
    monkeypatch.setattr(my_cart_module, "_delete_stale_checked_out_cart_rows", lambda db, user_id: 0)
    monkeypatch.setattr(my_cart_module, "CartProductModel", SimpleNamespace(customer_id=ColumnProbe()))
    monkeypatch.setattr(my_cart_module, "select", lambda model: FakeSelect())
    monkeypatch.setattr(
        my_cart_module,
        "get_cart_total",
        lambda rows: CartProductTotalDto(
            all_item_active_prices=90000,
            all_promo_active_prices=0,
            total_all_active_prices=90000,
        ),
    )
    monkeypatch.setattr(my_cart_module, "redis_client", fake_redis)

    result = my_cart_module.my_cart(FakeDB(), "user-1")

    assert result.error is None
    assert result.data.data[0].product_id == "product-83"
    assert result.data.data[0].variant_id == 31
    assert fake_redis.read_keys == ["cart:user-1:0:100:v2"]
