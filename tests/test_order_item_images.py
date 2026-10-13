from app.models.order_item_model import OrderItemModel


class FakeVariant:
    img = "https://cdn.example.com/variant.webp"


class FakeProductImage:
    def __init__(self, id, url, is_primary=False, sort_order=0):
        self.id = id
        self.url = url
        self.is_primary = is_primary
        self.sort_order = sort_order


class FakeProduct:
    product_images = [
        FakeProductImage(2, "https://cdn.example.com/secondary.webp", False, 2),
        FakeProductImage(1, "https://cdn.example.com/primary.webp", True, 1),
    ]


def test_order_item_prefers_variant_image():
    item = OrderItemModel()
    item.pack_type = FakeVariant()
    item.products = FakeProduct()

    assert item.variant_image == "https://cdn.example.com/variant.webp"
    assert item.product_image == "https://cdn.example.com/primary.webp"
    assert item.image == "https://cdn.example.com/variant.webp"


def test_order_item_falls_back_to_primary_product_image():
    item = OrderItemModel()
    item.pack_type = None
    item.products = FakeProduct()

    assert item.image == "https://cdn.example.com/primary.webp"
