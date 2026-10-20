from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.dtos.error_response_dtos import ErrorResponseDto
from app.dtos.rating_dtos import (
    EligibleRatingVariantDto,
    EligibleRatingVariantsResponseDto,
)
from app.models.order_item_model import OrderItemModel
from app.models.order_model import OrderModel
from app.models.pack_type_model import PackTypeModel
from app.models.payment_model import PaymentModel
from app.models.product_model import ProductModel
from app.services.rating_services.purchase_eligibility import successful_transaction_condition
from app.services.rating_services.support_function import handle_db_error
from app.utils.result import Result, build


def format_variant_name(name: Optional[str], variant: Optional[str]) -> str:
    parts = [part.strip() for part in (name, variant) if part and part.strip()]
    return " • ".join(parts) if parts else "Produk tanpa varian"


def get_eligible_variant_rows(db: Session, product_id: str, user_id: str):
    rows = (
        db.query(
            OrderItemModel.variant_id,
            PackTypeModel.name,
            PackTypeModel.variant,
        )
        .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
        .outerjoin(PaymentModel, PaymentModel.order_id == OrderModel.id)
        .outerjoin(PackTypeModel, PackTypeModel.id == OrderItemModel.variant_id)
        .filter(
            OrderItemModel.product_id == product_id,
            OrderModel.customer_id == user_id,
            OrderModel.status == "completed",
            successful_transaction_condition(),
            or_(
                OrderItemModel.variant_id.is_(None),
                PackTypeModel.product_id == product_id,
            ),
        )
        .all()
    )

    unique_rows = {}
    for variant_id, name, variant in rows:
        unique_rows[variant_id] = (variant_id, name, variant)

    return [
        unique_rows[key]
        for key in sorted(unique_rows, key=lambda value: (value is None, value or 0))
    ]


def get_eligible_rating_variants(
    db: Session,
    product_id: str,
    user_id: str,
) -> Result[EligibleRatingVariantsResponseDto, Exception]:
    try:
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

        data = [
            EligibleRatingVariantDto(
                variant_id=variant_id,
                variant_name=format_variant_name(name, variant),
            )
            for variant_id, name, variant in get_eligible_variant_rows(db, product_id, user_id)
        ]
        return build(data=EligibleRatingVariantsResponseDto(data=data))
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
                    message="Varian pesanan belum bisa dimuat. Silakan coba lagi.",
                ).model_dump(),
            )
        )
