import os

from fastapi import HTTPException, status

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.dtos.error_response_dtos import ErrorResponseDto


def normalize_product_image_url(url: str | None) -> str | None:
    if not url:
        return url
    if "127.0.0.1" not in url and "localhost" not in url:
        return url
    host_url = os.getenv("HOST_URL", "").rstrip("/")
    if not host_url:
        railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway_domain:
            host_url = f"https://{railway_domain.strip('/')}"
    if not host_url:
        return url
    try:
        path = url.split("/images/", 1)[1]
        return f"{host_url}/images/{path}"
    except Exception:
        return url


# Utility Function for Handling Database Errors
def handle_db_error(db: Session, error: SQLAlchemyError) -> HTTPException:
    db.rollback()
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=ErrorResponseDto(
            status_code=status.HTTP_409_CONFLICT,
            error="Conflict",
            message="Data belum bisa diproses. Silakan coba beberapa saat lagi."
        ).dict()
    )
