# services/article_service.py

from fastapi import HTTPException, status

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models.article_model import ArticleModel
from app.dtos import article_dtos
from app.dtos.error_response_dtos import ErrorResponseDto

import json
import logging

from app.utils.result import build, Result
from app.utils.error_parser import find_errr_from_args
from app.libs.redis_config import custom_json_serializer, redis_client

logger = logging.getLogger(__name__)

CACHE_TTL = 3600
RESPONSE_MESSAGE = "All List of Articles accessed successfully"

def get_articles(
        db: Session,
        skip: int = 0,
        limit: int = 10
    ) -> Result[article_dtos.AllArticleResponseDto, Exception]:
    cache_key = f"articles:{skip}:{limit}"

    try:
        # Check if product data exists in Redis
        cached_article = None
        if redis_client:
            try:
                cached_article = redis_client.get(cache_key)
            except Exception as cache_error:
                logger.warning("Failed to read article cache for key %s: %s", cache_key, cache_error)

        if cached_article:
            cached_article_data = json.loads(cached_article)
            if all(isinstance(addr, dict) and addr.get('id') is not None for addr in cached_article_data):
                article_dto = [
                    article_dtos.GetAllArticleDTO(**addr)
                    for addr in cached_article_data
                ]
                return build(data=article_dtos.AllArticleResponseDto(
                    status_code=status.HTTP_200_OK,
                    message=RESPONSE_MESSAGE,
                    data=article_dto
                ))

            logger.info("Article cache key %s is stale, refreshing from database.", cache_key)
            try:
                redis_client.delete(cache_key)
            except Exception as cache_error:
                logger.warning("Failed to delete stale article cache for key %s: %s", cache_key, cache_error)

        article = db.execute(
            select(ArticleModel)
            .order_by(ArticleModel.display_id)
            .offset(skip)
            .limit(limit)
        ).scalars().all()

        if not article:
            return build(data=article_dtos.AllArticleResponseDto(
                status_code=status.HTTP_200_OK,
                message=RESPONSE_MESSAGE,
                data=[]
            ))

        # Konversi wishlist menjadi DTO
        article_dto = [
            article_dtos.GetAllArticleDTO(
                id=art.id,
                display_id=art.display_id,
                title=art.title,
                img=art.img,
                description_list=art.description_list
            )
            for art in article
        ]

        # Cache the data in Redis
        if redis_client:
            try:
                redis_client.setex(cache_key, CACHE_TTL, json.dumps(
                    [dto.dict() for dto in article_dto],
                    default=custom_json_serializer
                ))
            except Exception as cache_error:
                logger.warning("Failed to write article cache for key %s: %s", cache_key, cache_error)

        return build(data=article_dtos.AllArticleResponseDto(
            status_code=status.HTTP_200_OK,
            message=RESPONSE_MESSAGE,
            data=article_dto
        ))

    except SQLAlchemyError as e:
        db.rollback()
        return build(error= HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorResponseDto(
                status_code=status.HTTP_409_CONFLICT,
                error="Conflict",
                message="Data belum bisa disimpan karena konflik data. Silakan periksa kembali input."
            ).dict()
        ))

    except Exception as e:
        return build(error= HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponseDto(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error="Internal Server Error",
                message="Permintaan belum bisa diproses. Silakan coba beberapa saat lagi."
            ).dict()
        ))


def _article_admin_dto(article: ArticleModel) -> article_dtos.AdminArticleDTO:
    return article_dtos.AdminArticleDTO(
        id=article.id,
        display_id=article.display_id,
        title=article.title,
        img=article.img,
        description_list=article.description_list,
        is_published=article.is_published,
    )


def get_published_articles(db: Session) -> Result[article_dtos.AllArticleResponseDto, Exception]:
    """Return only published articles for the customer storefront."""
    try:
        articles = db.execute(
            select(ArticleModel)
            .where(ArticleModel.is_published.is_(True))
            .order_by(ArticleModel.display_id)
        ).scalars().all()
        data = [
            article_dtos.GetAllArticleDTO(
                id=article.id,
                display_id=article.display_id,
                title=article.title,
                img=article.img,
                description_list=article.description_list,
            )
            for article in articles
        ]
        return build(data=article_dtos.AllArticleResponseDto(
            status_code=status.HTTP_200_OK,
            message=RESPONSE_MESSAGE,
            data=data,
        ))
    except SQLAlchemyError:
        db.rollback()
        return build(error=HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorResponseDto(
                status_code=status.HTTP_409_CONFLICT,
                error="Conflict",
                message="Data belum bisa diambil karena konflik. Silakan coba lagi.",
            ).dict(),
        ))
    except Exception:
        return build(error=HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponseDto(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error="Internal Server Error",
                message="Artikel belum bisa dimuat. Silakan coba lagi beberapa saat lagi.",
            ).dict(),
        ))


def get_admin_articles(db: Session) -> Result[article_dtos.AdminArticlesResponseDTO, Exception]:
    """Return published and archived articles for authorized content management."""
    try:
        articles = db.execute(
            select(ArticleModel).order_by(ArticleModel.display_id)
        ).scalars().all()
        return build(data=article_dtos.AdminArticlesResponseDTO(
            status_code=status.HTTP_200_OK,
            message="Daftar artikel admin berhasil diambil",
            data=[_article_admin_dto(article) for article in articles],
        ))
    except SQLAlchemyError:
        db.rollback()
        return build(error=HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorResponseDto(
                status_code=status.HTTP_409_CONFLICT,
                error="Conflict",
                message="Data belum bisa diambil karena konflik. Silakan coba lagi.",
            ).dict(),
        ))
    except Exception:
        return build(error=HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponseDto(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error="Internal Server Error",
                message="Artikel belum bisa dimuat. Silakan coba lagi beberapa saat lagi.",
            ).dict(),
        ))


def update_article_publication(
    db: Session,
    article_id: int,
    is_published: bool,
) -> Result[article_dtos.ArticlePublicationResponseDTO, Exception]:
    """Reversibly publish or archive an article without deleting its record."""
    try:
        article = db.execute(
            select(ArticleModel).where(ArticleModel.id == article_id)
        ).scalars().first()
        if not article:
            return build(error=HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponseDto(
                    status_code=status.HTTP_404_NOT_FOUND,
                    error="Not Found",
                    message="Artikel tidak ditemukan.",
                ).dict(),
            ))

        article.is_published = is_published
        db.commit()
        db.refresh(article)

        from app.services.article_services.update_article import delete_cache_by_pattern
        delete_cache_by_pattern("articles:*")

        return build(data=article_dtos.ArticlePublicationResponseDTO(
            status_code=status.HTTP_200_OK,
            message="Artikel berhasil dipublikasikan." if is_published else "Artikel berhasil diarsipkan.",
            data=_article_admin_dto(article),
        ))
    except SQLAlchemyError:
        db.rollback()
        return build(error=HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorResponseDto(
                status_code=status.HTTP_409_CONFLICT,
                error="Conflict",
                message="Status artikel belum bisa diperbarui. Silakan coba lagi.",
            ).dict(),
        ))
    except Exception:
        db.rollback()
        return build(error=HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponseDto(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error="Internal Server Error",
                message="Status artikel belum bisa diperbarui. Silakan coba lagi.",
            ).dict(),
        ))
