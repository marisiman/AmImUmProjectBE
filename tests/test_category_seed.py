import importlib

from app.models.tag_category_model import TagCategoryModel

category_module = importlib.import_module("app.services.category_services.get_all_categories")


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, existing_id=None):
        self.existing_id = existing_id
        self.added = []
        self.commits = 0

    def execute(self, _statement):
        return _ScalarResult(self.existing_id)

    def add(self, model):
        self.added.append(model)

    def commit(self):
        self.commits += 1


def test_ensure_creative_craft_category_inserts_once(monkeypatch):
    deleted_patterns = []
    monkeypatch.setattr(category_module, "delete_cache_by_pattern", deleted_patterns.append)
    db = _FakeDb(existing_id=None)

    inserted = category_module.ensure_creative_craft_category(db)

    assert inserted is True
    assert db.commits == 1
    assert len(db.added) == 1
    assert isinstance(db.added[0], TagCategoryModel)
    assert db.added[0].name == "Aksesoris & Custom Craft"
    assert "sticker" in db.added[0].description
    assert "3D print" in db.added[0].description
    assert deleted_patterns == ["categories:*"]


def test_ensure_creative_craft_category_is_idempotent(monkeypatch):
    deleted_patterns = []
    monkeypatch.setattr(category_module, "delete_cache_by_pattern", deleted_patterns.append)
    db = _FakeDb(existing_id=7)

    inserted = category_module.ensure_creative_craft_category(db)

    assert inserted is False
    assert db.commits == 0
    assert db.added == []
    assert deleted_patterns == []
