from datetime import datetime, timezone
from importlib import import_module
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pydantic import ValidationError

from app.dtos.rating_dtos import RatingCreateDto, ReviewDataUpdateDTO
from app.libs.sql_alchemy_lib import Base
from app.models import OrderItemModel, OrderModel, ProductModel, RatingModel, UserModel
from app.models.enums import DeliveryTypeEnum
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
                [("verified_high", "Aris"), ("verified_low", "Budi"), ("legacy", "Citra"), ("wrong_product", "Dina"), ("unfinished", "Eka")],
                start=1,
            )
        }
        products = [
            ProductModel(id=product_id, name="Produk Uji", weight=10, price=10000, product_by_id=1, is_active=True),
            ProductModel(id=other_product_id, name="Produk Lain", weight=10, price=10000, product_by_id=1, is_active=True),
        ]
        session.add_all([*users.values(), *products])
        session.flush()

        def add_order(user_key, order_product_id, status, day):
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
                    quantity=1,
                    price_per_item=10000,
                    total_price=10000,
                )
            )
            return order

        add_order("verified_high", product_id, "completed", 1)
        add_order("verified_low", product_id, "completed", 2)
        add_order("wrong_product", other_product_id, "completed", 3)
        add_order("unfinished", product_id, "processing", 4)
        session.flush()

        session.add_all(
            [
                RatingModel(id=1, product_id=product_id, user_id=users["verified_high"].id, rate=5, review="Cocok", created_at=datetime(2026, 2, 1, tzinfo=timezone.utc)),
                RatingModel(id=2, product_id=product_id, user_id=users["verified_low"].id, rate=3, review=None, created_at=datetime(2026, 2, 2, tzinfo=timezone.utc)),
                RatingModel(id=3, product_id=product_id, user_id=users["legacy"].id, rate=1, review="Legacy tanpa bukti", created_at=datetime(2026, 2, 3, tzinfo=timezone.utc)),
                RatingModel(id=4, product_id=product_id, user_id=users["wrong_product"].id, rate=2, review="Beli produk lain", created_at=datetime(2026, 2, 4, tzinfo=timezone.utc)),
                RatingModel(id=5, product_id=product_id, user_id=users["unfinished"].id, rate=1, review="Belum selesai", created_at=datetime(2026, 2, 5, tzinfo=timezone.utc)),
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

    assert second_page.error is None
    assert second_page.unwrap().data[0].id == 1
    assert second_page.unwrap().has_more is False


def test_duplicate_legacy_rows_use_latest_created_review_not_highest_id(rating_db):
    db, product_id = rating_db
    original = db.query(RatingModel).filter(RatingModel.id == 1).one()
    duplicate = RatingModel(
        id=6,
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


def test_rating_review_text_limit_matches_existing_database_column():
    with pytest.raises(ValidationError):
        RatingCreateDto(rate=5, review="x" * 101)
    with pytest.raises(ValidationError):
        ReviewDataUpdateDTO(rate=4, review="x" * 101)


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
