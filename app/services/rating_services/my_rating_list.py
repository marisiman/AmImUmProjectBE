from fastapi import HTTPException, status

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, DataError, IntegrityError

import logging
import json

from app.libs.redis_config import custom_json_serializer, redis_client

from app.models.rating_model import RatingModel
from app.models.pack_type_model import PackTypeModel
from app.services.rating_services.eligible_rating_variants import format_variant_name
from app.dtos.rating_dtos import MyRatingListDto, AllMyRatingListResponseDto
from app.dtos.error_response_dtos import ErrorResponseDto

from app.services.rating_services.support_function import handle_db_error

from app.utils.result import build, Result

logger = logging.getLogger(__name__)
CACHE_TTL = 3600
RATING_LIST_CACHE_PREFIX = "ratinglists:v3"
# Keep generation tokens persistent: expiring one could make an old page key valid again.
RATING_LIST_GENERATION_PREFIX = "ratinglist-generation:v1"


def _rating_list_generation_key(user_id: str) -> str:
    return f"{RATING_LIST_GENERATION_PREFIX}:{user_id}"


def invalidate_my_rating_list_cache(user_id: str) -> None:
    """Best-effort version bump and cleanup for every cached rating-list page."""
    if not redis_client:
        return

    try:
        redis_client.incr(_rating_list_generation_key(user_id))
    except Exception as cache_error:
        logger.warning(
            "rating_list_cache_generation_failed user_id=%s error_type=%s",
            user_id,
            type(cache_error).__name__,
        )

    try:
        for key in redis_client.scan_iter(f"{RATING_LIST_CACHE_PREFIX}:{user_id}:*"):
            redis_client.delete(key)
    except Exception as cache_error:
        logger.warning(
            "rating_list_cache_invalidation_failed user_id=%s error_type=%s",
            user_id,
            type(cache_error).__name__,
        )


def my_rating_list(
        db: Session,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> Result[AllMyRatingListResponseDto, Exception]:  # Mengembalikan List DTO
    try:
        # Redis is a cache only; a generation key keeps an old in-flight read from
        # becoming visible again after a concurrent rating mutation.
        redis_key = None
        cached_rates = None
        if redis_client:
            try:
                generation = redis_client.get(_rating_list_generation_key(user_id))
                generation = int(generation) if generation is not None else 0
                redis_key = f"{RATING_LIST_CACHE_PREFIX}:{user_id}:{generation}:{skip}:{limit}"
                cached_rates = redis_client.get(redis_key)
            except Exception as cache_error:
                logger.warning(
                    "rating_list_cache_read_failed user_id=%s error_type=%s",
                    user_id,
                    type(cache_error).__name__,
                )
                redis_key = None

        if cached_rates:
            try:
                cached_payload = json.loads(cached_rates)
                if not isinstance(cached_payload, list):
                    raise ValueError("cached rating list is not an array")
                all_rate_products_dto = [
                    MyRatingListDto(**addr)
                    for addr in cached_payload
                ]
            except Exception as cache_error:
                logger.warning(
                    "rating_list_cache_payload_invalid user_id=%s error_type=%s",
                    user_id,
                    type(cache_error).__name__,
                )
            else:
                return build(data=AllMyRatingListResponseDto(
                    status_code=status.HTTP_200_OK,
                    message="All lists of rating product successfully retrieved (from cache)",
                    data=all_rate_products_dto
                ))

        # Query untuk mengambil produk berdasarkan product_by_id
        rate_model = (
            db.query(RatingModel, PackTypeModel.name, PackTypeModel.variant)
            .outerjoin(PackTypeModel, PackTypeModel.id == RatingModel.variant_id)
            .filter(RatingModel.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

        if not rate_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_404_NOT_FOUND,
                    error="Not Found",
                    message=f"list rate of products from this user ID : {user_id} not found"
                ).dict()
            )

        # Konversi produk ke DTO
        all_rate_products_dto = [
            MyRatingListDto(
                id=rate_count.id,
                rate=rate_count.rate,
                review=rate_count.review,
                product_name=rate_count.product_name,
                variant_name=(
                    format_variant_name(variant_name, variant_type)
                    if rate_count.variant_id is not None and variant_name
                    else None
                ),
                created_at=rate_count.created_at,
            )
            for rate_count, variant_name, variant_type in rate_model
        ]

        # Cache is an optimization only; DB reads remain authoritative.
        if redis_client and redis_key:
            try:
                redis_client.setex(
                    redis_key,
                    CACHE_TTL,
                    json.dumps(
                        [dto.model_dump() for dto in all_rate_products_dto],
                        default=custom_json_serializer,
                    ),
                )
            except Exception as cache_error:
                logger.warning(
                    "rating_list_cache_write_failed user_id=%s error=%s",
                    user_id,
                    cache_error,
                )

        # return build(data=all_rate_products_dto)
        return build(data=AllMyRatingListResponseDto(
            status_code=status.HTTP_200_OK,
            message="All List of your rating products accessed successfully",
            data=all_rate_products_dto
        ))

    # Error SQLAlchemy untuk data yang tidak valid, seperti id tidak ditemukan
    except IntegrityError as ie:
        db.rollback()
        return build(error=HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorResponseDto(
                status_code=status.HTTP_409_CONFLICT,
                error="Conflict",
                message="Data belum bisa diproses karena konflik data. Silakan coba beberapa saat lagi."
            ).dict()
        ))

    # Error SQLAlchemy untuk data input yang tidak sesuai tipe
    except DataError as de:
        db.rollback()
        return build(error=HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorResponseDto(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                error="Unprocessable Entity",
                message="Data belum valid. Silakan periksa kembali input."
            ).dict()
        ))

    except SQLAlchemyError as e:
        return handle_db_error(db, e)

    except HTTPException as http_ex:
        return build(error=http_ex)

        # Error tipe data tidak valid (misal, `skip` atau `limit` bukan integer)
    except (ValueError, TypeError) as te:
        return build(error=HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorResponseDto(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                error="Unprocessable Entity",
                message="Input belum valid. Silakan periksa kembali data yang dikirim."
            ).dict()
        ))

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
