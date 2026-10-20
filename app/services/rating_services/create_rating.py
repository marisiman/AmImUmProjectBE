import uuid

from fastapi import HTTPException, status

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models.product_model import ProductModel
from app.models.order_model import OrderModel
from app.models.order_item_model import OrderItemModel
from app.models.rating_model import RatingModel
from app.dtos.rating_dtos import RatingCreateOfIdProductDto, RatingCreateDto, RatingInfoCreateDto, RatingResponseCreateDto
from app.dtos.error_response_dtos import ErrorResponseDto
from app.services.rating_services.eligible_rating_variants import (
    format_variant_name,
    get_eligible_variant_rows,
)

from app.services.rating_services.support_function import handle_db_error

from app.utils.result import build, Result

def create_rating(
        db: Session,
        # product_id: uuid.UUID,
        rate: RatingCreateOfIdProductDto,
        create_rate: RatingCreateDto,
        user_id: str
) -> Result[RatingModel, Exception]:
    try:
        # Cek apakah product_id ada di tabel products
        product = (
            db.query(ProductModel)
            .filter(ProductModel.id == str(rate.product_id))
            .with_for_update()
            .first()
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_404_NOT_FOUND,
                    error="Not Found",
                    message=f"Information about product with ID {str(rate.product_id)} not found."
                ).dict()
            )

        eligible_variants = get_eligible_variant_rows(db, str(rate.product_id), user_id)
        eligible_variant_ids = {row[0] for row in eligible_variants}
        if not eligible_variants:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_403_FORBIDDEN,
                    error="Purchase Required",
                    message="Rating hanya dapat diberikan setelah pesanan produk berstatus selesai.",
                ).model_dump(),
            )

        if "variant_id" in create_rate.model_fields_set:
            selected_variant_id = create_rate.variant_id
            if selected_variant_id not in eligible_variant_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ErrorResponseDto(
                        status_code=status.HTTP_403_FORBIDDEN,
                        error="Purchased Variant Required",
                        message="Pilih varian yang benar-benar ada pada pesanan selesai Anda.",
                    ).model_dump(),
                )
        else:
            if len(eligible_variant_ids) != 1:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=ErrorResponseDto(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        error="Variant Selection Required",
                        message="Pilih varian yang dibeli sebelum mengirim rating.",
                    ).model_dump(),
                )
            selected_variant_id = next(iter(eligible_variant_ids))

        selected_variant = next(
            (row for row in eligible_variants if row[0] == selected_variant_id),
            None,
        )
        variant_name = (
            format_variant_name(selected_variant[1], selected_variant[2])
            if selected_variant and selected_variant_id is not None
            else None
        )

        existing_rating = (
            db.query(RatingModel)
            .filter(
                RatingModel.product_id == str(rate.product_id),
                RatingModel.user_id == user_id,
            )
            .first()
        )
        if existing_rating:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_409_CONFLICT,
                    error="Rating Already Exists",
                    message="Anda sudah memberi rating untuk produk ini. Silakan perbarui rating yang sudah ada.",
                ).model_dump(),
            )

        rate_instance = RatingModel(
            **create_rate.model_dump(exclude={"variant_id"}),
            variant_id=selected_variant_id,
        )
        rate_instance.product_id = str(rate.product_id)  # Konversi UUID ke string
        rate_instance.user_id = user_id
        db.add(rate_instance)
        db.commit()
        db.refresh(rate_instance)

        create_rate_response = RatingInfoCreateDto(
            id=rate_instance.id,
            rate=rate_instance.rate,
            review=rate_instance.review,
            product_name=rate_instance.product_name,
            rater_name=rate_instance.rater_name,
            variant_name=variant_name,
            created_at=rate_instance.created_at
        )

        return build(data=RatingResponseCreateDto(
            status_code=201,
            message="Your rating for the product has been created",
            data=create_rate_response
        ))

    except SQLAlchemyError as e:
        return handle_db_error(db, e)

    except HTTPException as http_ex:
        db.rollback()  # Rollback jika terjadi error dari Firebase
        return build(error=http_ex)

    except Exception as e:
        db.rollback()
        return build(error= HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponseDto(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error="Internal Server Error",
                message="Permintaan belum bisa diproses. Silakan coba beberapa saat lagi."
            ).dict()
        ))
