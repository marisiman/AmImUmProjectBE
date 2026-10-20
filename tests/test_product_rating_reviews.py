from datetime import datetime, timezone
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pydantic import ValidationError

from app.dtos.rating_dtos import (
    DeleteReviewDto,
    RatingCreateDto,
    RatingCreateOfIdProductDto,
    ReviewDataUpdateDTO,
    ReviewIdToUpdateDto,
)
from app.libs.sql_alchemy_lib import Base
from app.models import OrderItemModel, OrderModel, ProductModel, RatingModel, UserModel
from app.models.pack_type_model import PackTypeModel
from app.models.payment_model import PaymentModel
from app.models.enums import DeliveryTypeEnum, FraudStatusEnum, TransactionStatusEnum
from app.services.rating_services.create_rating import create_rating
import app.models  # noqa: F401 - register all FK tables on shared metadata

rating_service = import_module("app.services.rating_services.get_product_ratings")


@pytest.fixture
def rating_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        product_id = str(uuid4())
        other_product_id = str(uuid4())
        users = {
            key: UserModel(
                id=str(uuid4()),
                firstname=name,
                email=f"{key}@example.test",
                phone=f"+62000{index:04d}",
                role="user",
                is_active=True,
            )
            for index, (key, name) in enumerate(
                [("verified_high", "Aris"), ("verified_low", "Budi"), ("legacy", "Citra"), ("wrong_product", "Dina"), ("unfinished", "Eka"), ("verified_new", "Fajar"), ("verified_legacy", "Gita"), ("verified_multi", "Hana"), ("verified_mismatch", "Iwan"), ("verified_payment_pending", "Joko"), ("verified_capture", "Kiki"), ("verified_capture_challenge", "Lala"), ("verified_no_variant", "Maya")],
                start=1,
            )
        }
        products = [
            ProductModel(id=product_id, name="Produk Uji", weight=10, price=10000, product_by_id=1, is_active=True),
            ProductModel(id=other_product_id, name="Produk Lain", weight=10, price=10000, product_by_id=1, is_active=True),
        ]
        variants = [
            PackTypeModel(id=101, product_id=product_id, name="Tanpa Lampu", min_amount=1, variant="Type_01", stock=10, price=10000),
            PackTypeModel(id=102, product_id=product_id, name="Dengan Lampu", min_amount=1, variant="Type_02", stock=10, price=15000),
            PackTypeModel(id=201, product_id=other_product_id, name="Varian lain", min_amount=1, variant="Type_01", stock=10, price=10000),
        ]
        session.add_all([*users.values(), *products, *variants])
        session.flush()

        def add_order(user_key, order_product_id, status, day, variant_id=None):
            order = OrderModel(
                id=str(uuid4()),
                customer_id=users[user_key].id,
                status=status,
                total_price=10000,
                delivery_type=DeliveryTypeEnum.delivery,
                created_at=datetime(2026, 1, day, tzinfo=timezone.utc),
                updated_at=datetime(2026, 1, day, tzinfo=timezone.utc),
            )
            session.add(order)
            session.flush()
            session.add(
                OrderItemModel(
                    order_id=order.id,
                    product_id=order_product_id,
                    variant_id=variant_id,
                    quantity=1,
                    price_per_item=10000,
                    total_price=10000,
                )
            )
            return order

        add_order("verified_high", product_id, "completed", 1, variant_id=101)
        add_order("verified_low", product_id, "completed", 2, variant_id=102)
        add_order("wrong_product", other_product_id, "completed", 3, variant_id=201)
        add_order("unfinished", product_id, "processing", 4, variant_id=101)
        settled_order = add_order("verified_new", product_id, "completed", 6, variant_id=101)
        add_order("verified_legacy", product_id, "completed", 7, variant_id=101)
        add_order("verified_multi", product_id, "completed", 8, variant_id=101)
        add_order("verified_multi", product_id, "completed", 9, variant_id=102)
        add_order("verified_mismatch", product_id, "completed", 10, variant_id=101)
        pending_payment_order = add_order("verified_payment_pending", product_id, "completed", 11, variant_id=101)
        capture_order = add_order("verified_capture", product_id, "completed", 12, variant_id=102)
        challenged_order = add_order("verified_capture_challenge", product_id, "completed", 13, variant_id=101)
        add_order("verified_no_variant", product_id, "completed", 14)
        for payment_order, transaction_status, fraud_status in (
            (settled_order, TransactionStatusEnum.settlement, None),
            (pending_payment_order, TransactionStatusEnum.pending, None),
            (capture_order, TransactionStatusEnum.capture, FraudStatusEnum.accept),
            (challenged_order, TransactionStatusEnum.capture, FraudStatusEnum.challenge),
        ):
            session.add(PaymentModel(
                id=str(uuid4()),
                order_id=payment_order.id,
                transaction_id=f"test-tx-{payment_order.customer_id}",
                gross_amount=10000,
                transaction_status=transaction_status,
                fraud_status=fraud_status,
            ))
        session.flush()

        session.add_all(
            [
                RatingModel(id=1, product_id=product_id, user_id=users["verified_high"].id, variant_id=101, rate=5, review="Cocok", created_at=datetime(2026, 2, 1, tzinfo=timezone.utc)),
                RatingModel(id=2, product_id=product_id, user_id=users["verified_low"].id, variant_id=102, rate=3, review=None, created_at=datetime(2026, 2, 2, tzinfo=timezone.utc)),
                RatingModel(id=3, product_id=product_id, user_id=users["legacy"].id, rate=1, review="Legacy tanpa bukti", created_at=datetime(2026, 2, 3, tzinfo=timezone.utc)),
                RatingModel(id=4, product_id=product_id, user_id=users["wrong_product"].id, rate=2, review="Beli produk lain", created_at=datetime(2026, 2, 4, tzinfo=timezone.utc)),
                RatingModel(id=5, product_id=product_id, user_id=users["unfinished"].id, rate=1, review="Belum selesai", created_at=datetime(2026, 2, 5, tzinfo=timezone.utc)),
                RatingModel(id=6, product_id=product_id, user_id=users["verified_mismatch"].id, variant_id=102, rate=1, review="Varian tidak dibeli", created_at=datetime(2026, 2, 6, tzinfo=timezone.utc)),
                RatingModel(id=7, product_id=product_id, user_id=users["verified_payment_pending"].id, variant_id=101, rate=2, review="Transaksi belum berhasil", created_at=datetime(2026, 2, 7, tzinfo=timezone.utc)),
                RatingModel(id=9, product_id=product_id, user_id=users["verified_high"].id, variant_id=102, rate=1, review="Varian lain di waktu sama", created_at=datetime(2026, 2, 1, tzinfo=timezone.utc)),
            ]
        )
        session.commit()
        yield session, product_id
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_public_rating_summary_and_pages_include_only_completed_matching_purchases(rating_db):
    db, product_id = rating_db

    first_page = rating_service.get_product_ratings(db, product_id, skip=0, limit=1)
    second_page = rating_service.get_product_ratings(db, product_id, skip=1, limit=1)

    assert first_page.error is None
    payload = first_page.unwrap()
    assert payload.summary.avg_rating == 4.0
    assert payload.summary.total_rater == 2
    assert payload.summary.rating_distribution == {1: 0, 2: 0, 3: 1, 4: 0, 5: 1}
    assert payload.has_more is True
    assert len(payload.data) == 1
    assert payload.data[0].id == 2
    assert payload.data[0].rater_name == "B***"
    assert payload.data[0].verified_purchase is True
    assert payload.data[0].review is None
    assert payload.data[0].variant_name == "Dengan Lampu • Type_02"

    assert second_page.error is None
    assert second_page.unwrap().data[0].id == 1
    assert second_page.unwrap().data[0].variant_name == "Tanpa Lampu • Type_01"
    assert second_page.unwrap().has_more is False


def test_public_reviews_include_rating_for_completed_item_without_variant(rating_db):
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_no_variant@example.test").scalar()
    order_item = (
        db.query(OrderItemModel)
        .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
        .filter(OrderModel.customer_id == user_id, OrderItemModel.product_id == product_id)
        .one()
    )

    created = create_rating(
        db,
        RatingCreateOfIdProductDto(product_id=UUID(product_id)),
        RatingCreateDto(
            rate=4,
            review="Produk tanpa varian",
            order_item_id=order_item.id,
            variant_id=None,
        ),
        user_id,
    )

    assert created.error is None
    public_reviews = rating_service.get_product_ratings(db, product_id, skip=0, limit=10)

    assert public_reviews.error is None
    payload = public_reviews.unwrap()
    assert payload.summary.total_rater == 3
    assert any(
        review.id == created.unwrap().data.id and review.verified_purchase
        for review in payload.data
    )


def test_public_reviews_count_each_verified_order_item_for_the_same_buyer(rating_db):
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_multi@example.test").scalar()
    items = (
        db.query(OrderItemModel)
        .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
        .filter(OrderModel.customer_id == user_id, OrderItemModel.product_id == product_id)
        .order_by(OrderItemModel.id)
        .all()
    )
    assert len(items) == 2
    db.add_all([
        RatingModel(
            id=20,
            product_id=product_id,
            user_id=user_id,
            variant_id=items[0].variant_id,
            order_item_id=items[0].id,
            rate=5,
            review="Pesanan pertama",
            created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        ),
        RatingModel(
            id=21,
            product_id=product_id,
            user_id=user_id,
            variant_id=items[1].variant_id,
            order_item_id=items[1].id,
            rate=4,
            review="Pesanan berikutnya",
            created_at=datetime(2026, 3, 2, tzinfo=timezone.utc),
        ),
    ])
    db.commit()

    result = rating_service.get_product_ratings(db, product_id, skip=0, limit=10)

    assert result.error is None
    payload = result.unwrap()
    assert payload.summary.total_rater == 4
    assert {item.id for item in payload.data} >= {20, 21}


def test_duplicate_legacy_rows_use_latest_created_review_not_highest_id(rating_db):
    db, product_id = rating_db
    original = db.query(RatingModel).filter(RatingModel.id == 1).one()
    duplicate = RatingModel(
        id=8,
        product_id=product_id,
        user_id=original.user_id,
        rate=4,
        review="Rating legacy dengan ID lebih besar",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db.add(duplicate)
    db.commit()

    result = rating_service.get_product_ratings(db, product_id, skip=0, limit=10)

    assert result.error is None
    payload = result.unwrap()
    assert payload.summary.total_rater == 2
    assert payload.summary.avg_rating == 4.0
    assert payload.summary.rating_distribution == {1: 0, 2: 0, 3: 1, 4: 0, 5: 1}
    assert [item.id for item in payload.data] == [2, 1]


def test_rating_filter_changes_rows_but_keeps_overall_verified_summary(rating_db):
    db, product_id = rating_db

    result = rating_service.get_product_ratings(db, product_id, skip=0, limit=10, rate=3)

    assert result.error is None
    payload = result.unwrap()
    assert [item.rate for item in payload.data] == [3]
    assert payload.summary.total_rater == 2
    assert payload.has_more is False


def test_rating_write_persists_the_variant_bought_in_a_completed_order(rating_db):
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_new@example.test").scalar()

    result = create_rating(
        db,
        RatingCreateOfIdProductDto(product_id=UUID(product_id)),
        RatingCreateDto(rate=5, review="Varian sesuai", variant_id=101),
        user_id,
    )

    assert result.error is None
    saved_rating = db.query(RatingModel).filter(RatingModel.user_id == user_id).one()
    assert saved_rating.variant_id == 101
    assert result.unwrap().data.variant_name == "Tanpa Lampu • Type_01"


def test_same_product_can_be_rated_once_for_each_completed_order_item(rating_db):
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_multi@example.test").scalar()
    order_items = (
        db.query(OrderItemModel)
        .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
        .filter(OrderModel.customer_id == user_id, OrderItemModel.product_id == product_id)
        .order_by(OrderItemModel.id)
        .all()
    )
    assert len(order_items) == 2

    results = [
        create_rating(
            db,
            RatingCreateOfIdProductDto(product_id=UUID(product_id)),
            RatingCreateDto(
                rate=5,
                review=f"Pesanan item {item.id}",
                variant_id=item.variant_id,
                order_item_id=item.id,
            ),
            user_id,
        )
        for item in order_items
    ]

    assert all(result.error is None for result in results)
    assert db.query(RatingModel).filter(RatingModel.user_id == user_id).count() == 2

    duplicate = create_rating(
        db,
        RatingCreateOfIdProductDto(product_id=UUID(product_id)),
        RatingCreateDto(
            rate=4,
            review="Duplikat item pertama",
            variant_id=order_items[0].variant_id,
            order_item_id=order_items[0].id,
        ),
        user_id,
    )
    assert duplicate.error is not None
    assert getattr(duplicate.error, "status_code", None) == 409


def test_legacy_rating_write_auto_selects_a_single_purchased_variant(rating_db):
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_legacy@example.test").scalar()

    result = create_rating(
        db,
        RatingCreateOfIdProductDto(product_id=UUID(product_id)),
        RatingCreateDto(rate=4, review="Tetap kompatibel"),
        user_id,
    )

    assert result.error is None
    saved_rating = db.query(RatingModel).filter(RatingModel.user_id == user_id).one()
    assert saved_rating.variant_id == 101



def test_legacy_rating_write_requires_selection_when_multiple_variants_were_bought(rating_db):
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_multi@example.test").scalar()

    result = create_rating(
        db,
        RatingCreateOfIdProductDto(product_id=UUID(product_id)),
        RatingCreateDto(rate=4, review="Butuh pilihan"),
        user_id,
    )

    assert result.error is not None
    assert getattr(result.error, "status_code", None) == 422
    assert db.query(RatingModel).filter(RatingModel.user_id == user_id).count() == 0



def test_rating_write_rejects_a_variant_not_in_the_buyers_completed_order(rating_db):
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_new@example.test").scalar()

    result = create_rating(
        db,
        RatingCreateOfIdProductDto(product_id=UUID(product_id)),
        RatingCreateDto(rate=5, review="Varian diuji", variant_id=102),
        user_id,
    )

    assert result.error is not None
    assert getattr(result.error, "status_code", None) == 403
    assert db.query(RatingModel).filter(RatingModel.user_id == user_id).count() == 0



def test_rating_write_rejects_a_completed_order_with_pending_transaction(rating_db):
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_payment_pending@example.test").scalar()

    result = create_rating(
        db,
        RatingCreateOfIdProductDto(product_id=UUID(product_id)),
        RatingCreateDto(rate=5, review="Transaksi belum lunas", variant_id=101),
        user_id,
    )

    assert result.error is not None
    assert getattr(result.error, "status_code", None) == 403
    error_detail = getattr(result.error, "detail", {})
    assert error_detail["message"] == (
        "Rating hanya dapat diberikan untuk item pesanan yang selesai dan pembayarannya berhasil."
    )
    assert db.query(RatingModel).filter(RatingModel.user_id == user_id).count() == 1



def test_rating_review_text_limit_matches_existing_database_column():
    with pytest.raises(ValidationError):
        RatingCreateDto(rate=5, review="x" * 101)
    with pytest.raises(ValidationError):
        ReviewDataUpdateDTO(rate=4, review="x" * 101)


def test_my_rating_list_includes_the_recorded_variant_name(monkeypatch, rating_db):
    service = import_module("app.services.rating_services.my_rating_list")
    db, _ = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_high@example.test").scalar()
    monkeypatch.setattr(service.redis_client, "get", lambda _key: None)
    monkeypatch.setattr(service.redis_client, "setex", lambda *_args: None)

    result = service.my_rating_list(db, user_id)

    assert result.error is None
    assert result.unwrap().data[0].variant_name == "Tanpa Lampu • Type_01"



def test_eligible_variant_list_requires_a_completed_order_and_successful_transaction(rating_db):
    from app.services.rating_services.eligible_rating_variants import get_eligible_rating_variants

    db, product_id = rating_db
    multi_user_id = db.query(UserModel.id).filter(UserModel.email == "verified_multi@example.test").scalar()
    unfinished_user_id = db.query(UserModel.id).filter(UserModel.email == "unfinished@example.test").scalar()
    pending_payment_user_id = db.query(UserModel.id).filter(UserModel.email == "verified_payment_pending@example.test").scalar()
    capture_user_id = db.query(UserModel.id).filter(UserModel.email == "verified_capture@example.test").scalar()
    challenged_user_id = db.query(UserModel.id).filter(UserModel.email == "verified_capture_challenge@example.test").scalar()

    purchased = get_eligible_rating_variants(db, product_id, multi_user_id)
    unfinished = get_eligible_rating_variants(db, product_id, unfinished_user_id)
    pending_payment = get_eligible_rating_variants(db, product_id, pending_payment_user_id)
    captured = get_eligible_rating_variants(db, product_id, capture_user_id)
    challenged = get_eligible_rating_variants(db, product_id, challenged_user_id)

    assert purchased.error is None
    assert [variant.model_dump() for variant in purchased.unwrap().data] == [
        {"variant_id": 101, "variant_name": "Tanpa Lampu • Type_01"},
        {"variant_id": 102, "variant_name": "Dengan Lampu • Type_02"},
    ]
    assert unfinished.error is None
    assert unfinished.unwrap().data == []
    assert pending_payment.error is None
    assert pending_payment.unwrap().data == []
    assert captured.error is None
    assert [variant.variant_id for variant in captured.unwrap().data] == [102]
    assert challenged.error is None
    assert challenged.unwrap().data == []



def test_eligible_variant_route_is_registered_and_returns_only_authenticated_purchases(rating_db):
    from fastapi.testclient import TestClient

    from app.libs.jwt_lib import jwt_dto, jwt_service
    from app.libs.sql_alchemy_lib import get_db
    from app.main import app

    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_multi@example.test").scalar()
    url = f"/rating/product/{product_id}/eligible-variants"
    order_items_url = f"/rating/product/{product_id}/eligible-order-items"
    client = TestClient(app)

    unauthenticated = client.get(url)
    unauthenticated_order_items = client.get(order_items_url)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[jwt_service.get_jwt_pyload] = lambda: jwt_dto.TokenPayLoad(id=user_id, role="user")
    try:
        authenticated = client.get(url)
        authenticated_order_items = client.get(order_items_url)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(jwt_service.get_jwt_pyload, None)

    assert unauthenticated.status_code == 403
    assert authenticated.status_code == 200
    assert authenticated.json()["data"] == [
        {"variant_id": 101, "variant_name": "Tanpa Lampu • Type_01"},
        {"variant_id": 102, "variant_name": "Dengan Lampu • Type_02"},
    ]
    assert unauthenticated_order_items.status_code == 403
    assert authenticated_order_items.status_code == 200
    eligible_items = authenticated_order_items.json()["data"]
    expected_items = (
        db.query(OrderItemModel)
        .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
        .filter(OrderModel.customer_id == user_id, OrderItemModel.product_id == product_id)
        .all()
    )
    assert {item["order_item_id"] for item in eligible_items} == {item.id for item in expected_items}
    assert {item["variant_id"] for item in eligible_items} == {101, 102}
    assert all(item["order_id"] for item in eligible_items)
    assert all(item["order_date"] for item in eligible_items)



def test_public_product_ratings_route_supports_anonymous_filtered_read(rating_db):
    from fastapi.testclient import TestClient

    from app.libs.sql_alchemy_lib import get_db
    from app.main import app

    db, product_id = rating_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get(f"/rating/product/{product_id}?rate=3&limit=5")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_rater"] == 2
    assert len(payload["data"]) == 1
    assert payload["data"][0]["rate"] == 3
    assert payload["data"][0]["verified_purchase"] is True
    assert payload["data"][0]["rater_name"] == "B***"


def test_my_rating_list_falls_back_to_database_when_redis_is_unavailable(monkeypatch, rating_db):
    rating_list_service = import_module("app.services.rating_services.my_rating_list")
    db, _ = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_high@example.test").scalar()
    monkeypatch.setattr(rating_list_service, "redis_client", None)

    result = rating_list_service.my_rating_list(db, user_id)

    assert result.error is None
    expected_ids = {
        rating_id
        for (rating_id,) in db.query(RatingModel.id)
        .filter(RatingModel.user_id == user_id)
        .all()
    }
    assert {rating.id for rating in result.unwrap().data} == expected_ids


class _RatingCacheSpy:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.deleted: list[str] = []
        self.patterns: list[str] = []
        self.keys = [
            f"ratinglists:v3:{user_id}:0:0:100",
            "ratinglists:v3:another-user:0:0:100",
        ]
        self.generations = {}
        self.expirations = []

    def incr(self, key: str):
        self.generations[key] = self.generations.get(key, 0) + 1
        return self.generations[key]

    def expire(self, key: str, ttl: int):
        self.expirations.append((key, ttl))
        return True

    def scan_iter(self, pattern: str):
        self.patterns.append(pattern)
        prefix = pattern.removesuffix("*")
        return iter(key for key in self.keys if key.startswith(prefix))

    def delete(self, key: str):
        self.deleted.append(key)
        return 1


def test_create_rating_invalidates_the_users_cached_rating_list(monkeypatch, rating_db):
    cache_service = import_module("app.services.rating_services.my_rating_list")
    order_detail_service = import_module("app.services.order_services.detail_order")
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_new@example.test").scalar()
    order_id = (
        db.query(OrderModel.id)
        .join(OrderItemModel, OrderItemModel.order_id == OrderModel.id)
        .filter(OrderModel.customer_id == user_id, OrderItemModel.product_id == product_id)
        .scalar()
    )
    cache = _RatingCacheSpy(user_id)
    order_cache = _RatingCacheSpy(user_id)
    monkeypatch.setattr(cache_service, "redis_client", cache)
    monkeypatch.setattr(order_detail_service, "redis_client", order_cache)

    result = create_rating(
        db,
        RatingCreateOfIdProductDto(product_id=UUID(product_id)),
        RatingCreateDto(rate=5, review="Pembelian sesuai", variant_id=101),
        user_id,
    )

    assert result.error is None
    assert cache.generations == {f"ratinglist-generation:v1:{user_id}": 1}
    assert cache.patterns == [f"ratinglists:v3:{user_id}:*"]
    assert cache.deleted == [f"ratinglists:v3:{user_id}:0:0:100"]
    order_generation_key = f"order-detail-generation:v1:{user_id}:{order_id}"
    assert order_cache.generations == {order_generation_key: 1}
    assert order_cache.expirations == [(order_generation_key, order_detail_service.GENERATION_KEY_TTL)]


def test_edit_rating_invalidates_the_users_cached_rating_list(monkeypatch, rating_db):
    cache_service = import_module("app.services.rating_services.my_rating_list")
    edit_service = import_module("app.services.rating_services.edit_my_review")
    db, _ = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_high@example.test").scalar()
    cache = _RatingCacheSpy(user_id)
    monkeypatch.setattr(cache_service, "redis_client", cache)

    result = edit_service.edit_my_review(
        db,
        review_id_update=ReviewIdToUpdateDto(rating_id=1),
        review_update=ReviewDataUpdateDTO(rate=4, review="Ulasan diperbarui"),
        user_id=user_id,
    )

    assert result.error is None
    assert cache.generations == {f"ratinglist-generation:v1:{user_id}": 1}
    assert cache.patterns == [f"ratinglists:v3:{user_id}:*"]
    assert cache.deleted == [f"ratinglists:v3:{user_id}:0:0:100"]


def test_delete_rating_invalidates_the_users_cached_rating_list(monkeypatch, rating_db):
    cache_service = import_module("app.services.rating_services.my_rating_list")
    order_detail_service = import_module("app.services.order_services.detail_order")
    delete_service = import_module("app.services.rating_services.delete_my_review")
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_no_variant@example.test").scalar()
    order_item = (
        db.query(OrderItemModel)
        .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
        .filter(OrderModel.customer_id == user_id, OrderItemModel.product_id == product_id)
        .one()
    )
    db.add(RatingModel(
        id=99,
        product_id=product_id,
        user_id=user_id,
        order_item_id=order_item.id,
        rate=5,
        review="Rating untuk uji cache",
    ))
    db.commit()
    cache = _RatingCacheSpy(user_id)
    order_cache = _RatingCacheSpy(user_id)
    monkeypatch.setattr(cache_service, "redis_client", cache)
    monkeypatch.setattr(order_detail_service, "redis_client", order_cache)

    result = delete_service.delete_my_review(
        db,
        review_id_delete=DeleteReviewDto(rating_id=99),
        user_id=user_id,
    )

    assert result.error is None
    assert cache.generations == {f"ratinglist-generation:v1:{user_id}": 1}
    assert cache.patterns == [f"ratinglists:v3:{user_id}:*"]
    assert cache.deleted == [f"ratinglists:v3:{user_id}:0:0:100"]
    order_generation_key = f"order-detail-generation:v1:{user_id}:{order_item.order_id}"
    assert order_cache.generations == {order_generation_key: 1}
    assert order_cache.expirations == [(order_generation_key, order_detail_service.GENERATION_KEY_TTL)]


class _RatingCacheCommandFailure:
    def __init__(self, *, fail_get=False, fail_setex=False):
        self.fail_get = fail_get
        self.fail_setex = fail_setex

    def get(self, _key):
        if self.fail_get:
            raise RuntimeError("redis get unavailable")
        return None

    def setex(self, *_args):
        if self.fail_setex:
            raise RuntimeError("redis setex unavailable")


@pytest.mark.parametrize("cached_value", ["not-json", "[{}]", "{}"])
def test_my_rating_list_treats_malformed_cached_payload_as_a_miss(
    monkeypatch, rating_db, cached_value
):
    rating_list_service = import_module("app.services.rating_services.my_rating_list")
    db, _ = rating_db

    class MalformedCache:
        def get(self, key):
            if key.startswith("ratinglist-generation:"):
                return "0"
            return cached_value

        def setex(self, *_args):
            return None

    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_high@example.test").scalar()
    monkeypatch.setattr(rating_list_service, "redis_client", MalformedCache())

    result = rating_list_service.my_rating_list(db, user_id)

    assert result.error is None
    assert {rating.id for rating in result.unwrap().data} == {1, 9}


@pytest.mark.parametrize("failure", ["get", "setex"])
def test_my_rating_list_survives_redis_command_failures(monkeypatch, rating_db, failure):
    rating_list_service = import_module("app.services.rating_services.my_rating_list")
    db, _ = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_high@example.test").scalar()
    cache = _RatingCacheCommandFailure(
        fail_get=failure == "get",
        fail_setex=failure == "setex",
    )
    monkeypatch.setattr(rating_list_service, "redis_client", cache)

    result = rating_list_service.my_rating_list(db, user_id)

    assert result.error is None
    assert {rating.id for rating in result.unwrap().data} == {1, 9}


class _RatingCacheInvalidationFailure:
    def __init__(self, user_id: str, fail_at: str):
        self.user_id = user_id
        self.fail_at = fail_at

    def incr(self, _key: str):
        return 1

    def scan_iter(self, _pattern: str):
        if self.fail_at == "scan_iter":
            raise RuntimeError("redis scan unavailable")
        return iter([f"ratinglists:v3:{self.user_id}:0:0:100"])

    def delete(self, _key: str):
        if self.fail_at == "delete":
            raise RuntimeError("redis delete unavailable")
        return 1


@pytest.mark.parametrize("failure", ["scan_iter", "delete"])
def test_create_rating_succeeds_when_cache_invalidation_fails(monkeypatch, rating_db, failure):
    cache_service = import_module("app.services.rating_services.my_rating_list")
    db, product_id = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_new@example.test").scalar()
    monkeypatch.setattr(
        cache_service,
        "redis_client",
        _RatingCacheInvalidationFailure(user_id, failure),
    )

    result = create_rating(
        db,
        RatingCreateOfIdProductDto(product_id=UUID(product_id)),
        RatingCreateDto(rate=5, review="Pembelian sesuai", variant_id=101),
        user_id,
    )

    assert result.error is None
    assert db.query(RatingModel).filter(RatingModel.user_id == user_id).count() == 1


def test_my_rating_list_ignores_a_stale_page_written_after_cache_invalidation(monkeypatch, rating_db):
    rating_list_service = import_module("app.services.rating_services.my_rating_list")
    db, _ = rating_db
    user_id = db.query(UserModel.id).filter(UserModel.email == "verified_high@example.test").scalar()

    class ConcurrentMutationCache:
        def __init__(self):
            self.generation = 0
            self.values = {}
            self.raced = False
            self.generation_key = f"ratinglist-generation:v1:{user_id}"

        def get(self, key):
            if key == self.generation_key:
                return str(self.generation)
            return self.values.get(key)

        def setex(self, key, _ttl, value):
            if not self.raced:
                db.query(RatingModel).filter(RatingModel.id == 1).update(
                    {RatingModel.review: "Ulasan berubah saat pemuatan"}
                )
                db.commit()
                rating_list_service.invalidate_my_rating_list_cache(user_id)
                self.raced = True
            self.values[key] = value

        def incr(self, key):
            assert key == self.generation_key
            self.generation += 1
            return self.generation

        def scan_iter(self, pattern):
            prefix = pattern.removesuffix("*")
            return iter(key for key in self.values if key.startswith(prefix))

        def delete(self, key):
            self.values.pop(key, None)
            return 1

    cache = ConcurrentMutationCache()
    monkeypatch.setattr(rating_list_service, "redis_client", cache)

    first_result = rating_list_service.my_rating_list(db, user_id)
    second_result = rating_list_service.my_rating_list(db, user_id)

    assert first_result.error is None
    assert second_result.error is None
    updated_rating = next(rating for rating in second_result.unwrap().data if rating.id == 1)
    assert updated_rating.review == "Ulasan berubah saat pemuatan"
