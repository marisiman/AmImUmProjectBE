import asyncio
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

from fastapi import UploadFile
from PIL import Image

from app.models.product_image_model import ProductImageModel
from app.models.product_model import ProductModel
import importlib

upload_module = importlib.import_module("app.services.product_services.upload_product_image")


class FakeQuery:
    def __init__(self, value=None, all_value=None):
        self.value = value
        self.all_value = all_value or []

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.all_value


class FakeDB:
    def __init__(self, old_images):
        self.product = SimpleNamespace(id="product-1")
        self.old_images = old_images
        self.executed_deletes = 0
        self.added = []
        self.commits = 0

    def query(self, model):
        if model is ProductModel:
            return FakeQuery(value=self.product)
        if model is ProductImageModel:
            return FakeQuery(all_value=self.old_images)
        raise AssertionError(f"Unexpected model query: {model}")

    def execute(self, statement):
        self.executed_deletes += 1
        return None

    def add(self, model):
        self.added.append(model)

    def commit(self):
        self.commits += 1

    def refresh(self, model):
        model.id = 99
        model.created_at = datetime.now(timezone.utc)


def _image_upload_file() -> UploadFile:
    buffer = BytesIO()
    Image.new("RGB", (64, 64), color="green").save(buffer, format="PNG")
    buffer.seek(0)
    return UploadFile(filename="produk.png", file=buffer, headers={"content-type": "image/png"})


def test_upload_product_image_replaces_old_rows_and_cleans_old_media(monkeypatch):
    old_images = [
        SimpleNamespace(url="https://res.cloudinary.com/demo/image/upload/v1/amimum/products/product-1/old-a.webp"),
        SimpleNamespace(url="https://example.supabase.co/storage/v1/object/public/AmimumProject-storage/images/product_picture/old-b.webp"),
    ]
    db = FakeDB(old_images)
    deleted_urls = []

    monkeypatch.setattr(
        upload_module,
        "_upload_to_cloudinary",
        lambda image_bytes, product_id, public_id_seed: (
            "https://res.cloudinary.com/demo/image/upload/v1/amimum/products/product-1/new.webp",
            64,
            64,
        ),
    )
    monkeypatch.setattr(upload_module, "delete_media_url", lambda url: deleted_urls.append(url))
    monkeypatch.setattr(upload_module, "invalidate_product_cache", lambda product_id: None)

    result = asyncio.run(upload_module.upload_product_image(db, "product-1", _image_upload_file()))

    assert result.error is None
    assert db.executed_deletes == 1
    assert db.commits == 1
    assert len(db.added) == 1
    assert db.added[0].is_primary is True
    assert db.added[0].sort_order == 0
    assert deleted_urls == [image.url for image in old_images]
