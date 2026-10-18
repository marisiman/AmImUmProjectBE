import os

from fastapi import HTTPException, status

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import SQLAlchemyError

from typing import List, Type

from app.models.product_model import ProductModel
from app.models.product_image_model import ProductImageModel
from app.dtos.product_dtos import AllProductInfoDTO, AllProductInfoResponseDto
from app.dtos.error_response_dtos import ErrorResponseDto

from app.services.product_services.support_function import handle_db_error, normalize_product_image_url

from app.utils.result import build, Result


def search_product(
        db: Session,
        product_name: str,
        skip: int = 0,
        limit: int = 10
    ) -> Result[AllProductInfoResponseDto, Exception]:
    try:
        search_query = f"{product_name}%"

        product_model = (
            db.execute(
                select(ProductModel)
                .options(
                    selectinload(ProductModel.pack_type),
                    selectinload(ProductModel.product_images),
                )
                .filter(
                    ProductModel.name.ilike(search_query)
                )
                .offset(skip)
                .limit(limit)
            ).scalars().all()
        )
        if not product_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_404_NOT_FOUND,
                    error="Not Found",
                    message= f"No products found with name containing '{product_name}'."
                ).dict()
            )

        # Jika tidak ada produk ditemukan, kembalikan list kosong
        # if not product_model:
        #     return build(data=[])

        # Konversi produk menjadi DTO, cek `all_variants` agar tidak menyebabkan error jika None
        all_products_dto = [
            AllProductInfoDTO(
                id=product.id,
                name=product.name,
                price=float(product.price),
                min_variant_price=product.min_variant_price,
                max_variant_price=product.max_variant_price,
                brand_info=product.brand_info,
                primary_image_url=(
                    normalize_product_image_url(
                        next((image.url for image in product.product_images if image.is_primary), None)
                    )
                    or os.getenv("DEFAULT_PRODUCT_IMAGE_URL")
                ),
                gallery_images=[
                    {
                        "id": image.id,
                        "url": normalize_product_image_url(image.url),
                        "is_primary": image.is_primary,
                        "sort_order": image.sort_order,
                    }
                    for image in sorted(
                        product.product_images or [],
                        key=lambda image: (image.sort_order or 0, image.id or 0),
                    )
                ],
                all_variants=product.all_variants or [],
                created_at=product.created_at
            )
            for product in product_model
        ]

        # return build(data=all_products_dto)

        return build(data=AllProductInfoResponseDto(
            status_code=status.HTTP_200_OK,
            message=f"All List product search name containing '{product_name}' can accessed successfully",
            data=all_products_dto
        ))

    except SQLAlchemyError as e:
        return handle_db_error(db, e)

    except HTTPException as http_ex:
        db.rollback()
        return build(error=http_ex)

    except Exception as e:
        return build(error= HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponseDto(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error="Internal Server Error",
                message="Permintaan belum bisa diproses. Silakan coba beberapa saat lagi."
            ).dict()
        ))
