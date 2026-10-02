from types import SimpleNamespace


def test_my_cart_queries_only_active_items(monkeypatch):
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
    assert ("is_active", True) in where_args
    assert result.data.data == []
