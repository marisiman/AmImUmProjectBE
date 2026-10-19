import uuid
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class RatingCreateOfIdProductDto(BaseModel):
    product_id: uuid.UUID

class RatingCreateDto(BaseModel):
    rate: Optional[int] = Field(
        ge=1,
        le=5,
        description="Rating harus bernilai antara 1 dan 5."
    )
    review: Optional[str] = Field(default=None, max_length=100)

class RatingInfoCreateDto(BaseModel):
    id: int
    rate: Optional[int] = 0
    review: Optional[str] = None
    product_name: Optional[str] = None
    rater_name: Optional[str] = None
    created_at: datetime

class RatingResponseCreateDto(BaseModel):
    status_code: int = Field(default=201)
    message: str = Field(default="Your rate for some product has been created")
    data: RatingInfoCreateDto


class RatingAllResponseDto(BaseModel):
    id: int
    rate: int
    review: Optional[str] = None
    product_name: Optional[str] = None
    rater_name: Optional[str] = None
    created_at: datetime
    # updated_at: datetime

class ProductRatingDto(BaseModel):
    id: int
    rate: int
    review: str
    rater_name: Optional[str] = None

class MyRatingListDto(BaseModel):
    id: int
    rate: int
    review: Optional[str] = None
    product_name: Optional[str] = None
    created_at: datetime
    # updated_at: datetime

class AllMyRatingListResponseDto(BaseModel):
    status_code: int = Field(default=200)
    message: str = Field(default="updated info rating and review for this product id successfully")
    data: List[MyRatingListDto]

class ReviewIdToUpdateDto(BaseModel):
    rating_id:int

class ReviewDataUpdateDTO(BaseModel):
    rate: int = Field(ge=1, le=5)
    review: Optional[str] = Field(default=None, max_length=100)

class ReviewInfoUpdateResponseDto(BaseModel):
    status_code: int = Field(default=200)
    message: str = Field(default="updated info rating and review for this product id successfully")
    data: ReviewDataUpdateDTO

class DeleteReviewDto(BaseModel):
    rating_id:int

class InfoDeleteReviewDto(BaseModel):
    rating_id: int
    rate: int
    review: Optional[str] = None
    product_name: Optional[str] = None

class DeleteReviewResponseDto(BaseModel):
    status_code: int = Field(default=200)
    message: str = Field(default="Your article has been deleted")
    data: InfoDeleteReviewDto


class ProductRatingReviewDto(BaseModel):
    id: int
    rate: int
    review: Optional[str] = None
    rater_name: str = "Pembeli"
    created_at: datetime
    verified_purchase: bool = True


class ProductRatingSummaryDto(BaseModel):
    avg_rating: float = 0
    total_rater: int = 0
    rating_distribution: dict[int, int] = Field(default_factory=dict)


class ProductRatingsResponseDto(BaseModel):
    status_code: int = Field(default=200)
    message: str = Field(default="Rating pembeli terverifikasi berhasil dimuat.")
    summary: ProductRatingSummaryDto
    data: List[ProductRatingReviewDto]
    skip: int = 0
    limit: int = 10
    has_more: bool = False
