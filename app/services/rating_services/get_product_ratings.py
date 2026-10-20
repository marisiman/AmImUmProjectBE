from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.dtos.error_response_dtos import ErrorResponseDto
from app.dtos.rating_dtos import (
    ProductRatingReviewDto,
    ProductRatingSummaryDto,
    ProductRatingsResponseDto,
)
from app.models.order_item_model import OrderItemModel
from app.models.order_model import OrderModel
from app.models.product_model import ProductModel
from app.models.pack_type_model import PackTypeModel
from app.models.payment_model import PaymentModel
from app.models.rating_model import RatingModel
from app.models.user_model import UserModel
from app.services.rating_services.eligible_rating_variants import format_variant_name
from app.services.rating_services.purchase_eligibility import successful_transaction_condition
from app.services.rating_services.support_function import handle_db_error
from app.utils.result import Result, build

RatingSort = Literal["recent", "highest", "lowest"]


def _masked_name(firstname: str | None) -> str:
    normalized = (firstname or "").strip()
    return f"{normalized[0].upper()}***" if normalized else "Pembeli"


def get_product_ratings(
    db: Session,
    product_id: str,
    skip: int = 0,
    limit: int = 10,
    rate: int | None = None,
    sort: RatingSort = "recent",
) -> Result[ProductRatingsResponseDto, Exception]:
    try:
        if skip < 0 or not 1 <= limit <= 50 or (rate is not None and rate not in range(1, 6)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    error="Invalid Rating Query",
                    message="Filter rating atau pagination belum valid.",
                ).model_dump(),
            )

        product_exists = db.query(ProductModel.id).filter(ProductModel.id == product_id).first()
        if not product_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_404_NOT_FOUND,
                    error="Not Found",
                    message="Produk tidak ditemukan.",
                ).model_dump(),
            )

        legacy_verified_purchase_exists = (
            db.query(OrderItemModel.id)
            .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
            .outerjoin(PaymentModel, PaymentModel.order_id == OrderModel.id)
            .outerjoin(PackTypeModel, PackTypeModel.id == OrderItemModel.variant_id)
            .filter(
                OrderItemModel.product_id == RatingModel.product_id,
                OrderModel.customer_id == RatingModel.user_id,
                OrderModel.status == "completed",
                successful_transaction_condition(),
                or_(
                    RatingModel.variant_id.is_(None),
                    and_(
                        OrderItemModel.variant_id == RatingModel.variant_id,
                        PackTypeModel.product_id == RatingModel.product_id,
                    ),
                ),
            )
            .exists()
        )
        exact_order_item_verified_purchase_exists = (
            db.query(OrderItemModel.id)
            .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
            .outerjoin(PaymentModel, PaymentModel.order_id == OrderModel.id)
            .outerjoin(PackTypeModel, PackTypeModel.id == OrderItemModel.variant_id)
            .filter(
                OrderItemModel.id == RatingModel.order_item_id,
                OrderItemModel.product_id == RatingModel.product_id,
                OrderModel.customer_id == RatingModel.user_id,
                OrderModel.status == "completed",
                successful_transaction_condition(),
                or_(
                    and_(
                        OrderItemModel.variant_id.is_(None),
                        RatingModel.variant_id.is_(None),
                    ),
                    OrderItemModel.variant_id == RatingModel.variant_id,
                ),
                or_(
                    OrderItemModel.variant_id.is_(None),
                    PackTypeModel.product_id == RatingModel.product_id,
                ),
            )
            .exists()
        )
        verified_rating_filter = (
            RatingModel.product_id == product_id,
            or_(
                and_(
                    RatingModel.order_item_id.is_not(None),
                    exact_order_item_verified_purchase_exists,
                ),
                and_(
                    RatingModel.order_item_id.is_(None),
                    legacy_verified_purchase_exists,
                ),
            ),
        )
        ranked_verified_ratings = (
            db.query(
                RatingModel.id.label("rating_id"),
                func.row_number().over(
                    partition_by=(RatingModel.order_item_id, RatingModel.user_id),
                    order_by=(RatingModel.created_at.desc(), RatingModel.id.desc()),
                ).label("rating_rank"),
            )
            .filter(*verified_rating_filter)
            .subquery()
        )
        one_rating_per_order_item_filter = (
            RatingModel.product_id == product_id,
            RatingModel.id.in_(
                select(ranked_verified_ratings.c.rating_id).where(
                    ranked_verified_ratings.c.rating_rank == 1
                )
            ),
        )
        summary_fields = [
            func.count(RatingModel.id),
            func.avg(RatingModel.rate),
            *[
                func.coalesce(func.sum(case((RatingModel.rate == star, 1), else_=0)), 0)
                for star in range(1, 6)
            ],
        ]
        summary_row = (
            db.query(*summary_fields)
            .filter(*one_rating_per_order_item_filter)
            .one()
        )
        distribution = {
            star: int(summary_row[star + 1] or 0)
            for star in range(1, 6)
        }
        summary = ProductRatingSummaryDto(
            avg_rating=round(float(summary_row[1] or 0), 1),
            total_rater=int(summary_row[0] or 0),
            rating_distribution=distribution,
        )

        orderings = {
            "recent": (RatingModel.created_at.desc(), RatingModel.id.desc()),
            "highest": (RatingModel.rate.desc(), RatingModel.created_at.desc(), RatingModel.id.desc()),
            "lowest": (RatingModel.rate.asc(), RatingModel.created_at.desc(), RatingModel.id.desc()),
        }
        query = (
            db.query(
                RatingModel,
                UserModel.firstname,
                PackTypeModel.name,
                PackTypeModel.variant,
            )
            .join(UserModel, UserModel.id == RatingModel.user_id)
            .outerjoin(PackTypeModel, PackTypeModel.id == RatingModel.variant_id)
            .filter(*one_rating_per_order_item_filter)
        )
        if rate is not None:
            query = query.filter(RatingModel.rate == rate)

        rows = (
            query.order_by(*orderings[sort])
            .offset(skip)
            .limit(limit + 1)
            .all()
        )
        has_more = len(rows) > limit
        reviews = [
            ProductRatingReviewDto(
                id=rating.id,
                rate=rating.rate,
                review=rating.review,
                rater_name=_masked_name(firstname),
                variant_name=(
                    format_variant_name(variant_name, variant_type)
                    if rating.variant_id is not None and variant_name
                    else None
                ),
                created_at=rating.created_at,
                verified_purchase=True,
            )
            for rating, firstname, variant_name, variant_type in rows[:limit]
        ]

        return build(
            data=ProductRatingsResponseDto(
                status_code=status.HTTP_200_OK,
                message="Rating pembeli terverifikasi berhasil dimuat.",
                summary=summary,
                data=reviews,
                skip=skip,
                limit=limit,
                has_more=has_more,
            )
        )
    except SQLAlchemyError as error:
        return handle_db_error(db, error)
    except HTTPException as error:
        return build(error=error)
    except Exception:
        db.rollback()
        return build(
            error=HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    error="Internal Server Error",
                    message="Rating produk belum bisa dimuat. Silakan coba beberapa saat lagi.",
                ).model_dump(),
            )
        )
