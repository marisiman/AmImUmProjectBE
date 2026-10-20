import uuid

from fastapi import HTTPException, status

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models.product_model import ProductModel
from app.models.rating_model import RatingModel
from app.dtos.rating_dtos import RatingCreateOfIdProductDto, RatingCreateDto, RatingInfoCreateDto, RatingResponseCreateDto
from app.dtos.error_response_dtos import ErrorResponseDto
from app.services.rating_services.eligible_rating_variants import (
    format_variant_name,
    get_eligible_order_item_rows,
)
from app.services.rating_services.my_rating_list import invalidate_my_rating_list_cache
from app.services.order_services.detail_order import invalidate_order_detail_cache
from app.services.rating_services.support_function import handle_db_error
from app.utils.result import build, Result


def _rating_conflict(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=ErrorResponseDto(
            status_code=status.HTTP_409_CONFLICT,
            error="Rating Already Exists",
            message=message,
        ).model_dump(),
    )


def _is_order_item_unique_conflict(error: IntegrityError) -> bool:
    diagnostic = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    return diagnostic == "uq_ratings_order_item_id"


def _unexpected_integrity_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=ErrorResponseDto(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error="Internal Server Error",
            message="Rating belum bisa disimpan. Silakan coba beberapa saat lagi.",
        ).model_dump(),
    )


def create_rating(
    db: Session,
    rate: RatingCreateOfIdProductDto,
    create_rate: RatingCreateDto,
    user_id: str,
) -> Result[RatingModel, Exception]:
    try:
        product = db.query(ProductModel).filter(ProductModel.id == str(rate.product_id)).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_404_NOT_FOUND,
                    error="Not Found",
                    message=f"Information about product with ID {str(rate.product_id)} not found."
                ).dict()
            )

        eligible_order_items = get_eligible_order_item_rows(db, str(rate.product_id), user_id)
        if not eligible_order_items:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_403_FORBIDDEN,
                    error="Purchase Required",
                    message="Rating hanya dapat diberikan untuk item pesanan yang selesai dan pembayarannya berhasil.",
                ).model_dump(),
            )

        requested_order_item_id = create_rate.order_item_id
        if requested_order_item_id is None:
            selected_order_item = None
            if "variant_id" in create_rate.model_fields_set:
                matching_variant_items = [
                    row for row in eligible_order_items if row[3] == create_rate.variant_id
                ]
                if len(matching_variant_items) == 1:
                    selected_order_item = matching_variant_items[0]
                elif len(matching_variant_items) > 1:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=ErrorResponseDto(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            error="Order Item Selection Required",
                            message="Pilih item pesanan selesai yang ingin diberi rating.",
                        ).model_dump(),
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=ErrorResponseDto(
                            status_code=status.HTTP_403_FORBIDDEN,
                            error="Purchased Variant Required",
                            message="Varian rating harus sama dengan varian pada item pesanan yang dipilih.",
                        ).model_dump(),
                    )
            elif len(eligible_order_items) == 1:
                selected_order_item = eligible_order_items[0]
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=ErrorResponseDto(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        error="Order Item Selection Required",
                        message="Pilih item pesanan selesai yang ingin diberi rating.",
                    ).model_dump(),
                )
        else:
            selected_order_item = next(
                (row for row in eligible_order_items if row[0] == requested_order_item_id),
                None,
            )
            if selected_order_item is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ErrorResponseDto(
                        status_code=status.HTTP_403_FORBIDDEN,
                        error="Purchased Order Item Required",
                        message="Rating hanya dapat diberikan untuk item pesanan selesai milik akun Anda.",
                    ).model_dump(),
                )

        selected_variant_id = selected_order_item[3]
        if (
            "variant_id" in create_rate.model_fields_set
            and create_rate.variant_id != selected_variant_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_403_FORBIDDEN,
                    error="Purchased Variant Required",
                    message="Varian rating harus sama dengan varian pada item pesanan yang dipilih.",
                ).model_dump(),
            )

        existing_rating = (
            db.query(RatingModel)
            .filter(RatingModel.order_item_id == selected_order_item[0])
            .first()
        )
        if existing_rating:
            raise _rating_conflict(
                "Item pesanan ini sudah diberi rating. Anda dapat mengubah rating yang sudah ada."
            )

        variant_name = (
            format_variant_name(selected_order_item[4], selected_order_item[5])
            if selected_variant_id is not None
            else None
        )
        rate_instance = RatingModel(
            **create_rate.model_dump(exclude={"variant_id", "order_item_id"}),
            variant_id=selected_variant_id,
            order_item_id=selected_order_item[0],
        )
        rate_instance.product_id = str(rate.product_id)
        rate_instance.user_id = user_id
        db.add(rate_instance)
        db.commit()
        invalidate_my_rating_list_cache(user_id)
        invalidate_order_detail_cache(user_id, str(selected_order_item[1]))
        db.refresh(rate_instance)

        return build(data=RatingResponseCreateDto(
            status_code=201,
            message="Rating untuk item pesanan berhasil dibuat.",
            data=RatingInfoCreateDto(
                id=rate_instance.id,
                rate=rate_instance.rate,
                review=rate_instance.review,
                product_name=rate_instance.product_name,
                rater_name=rate_instance.rater_name,
                variant_name=variant_name,
                created_at=rate_instance.created_at,
            ),
        ))

    except IntegrityError as error:
        db.rollback()
        if _is_order_item_unique_conflict(error):
            return build(error=_rating_conflict(
                "Item pesanan ini sudah diberi rating. Anda dapat mengubah rating yang sudah ada."
            ))
        return build(error=_unexpected_integrity_error())
    except SQLAlchemyError as error:
        return handle_db_error(db, error)
    except HTTPException as http_error:
        db.rollback()
        return build(error=http_error)
    except Exception:
        db.rollback()
        return build(error=HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponseDto(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error="Internal Server Error",
                message="Permintaan belum bisa diproses. Silakan coba beberapa saat lagi."
            ).dict()
        ))
