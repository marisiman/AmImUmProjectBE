from typing import Any, Dict, Optional
import os

from sqlalchemy import Column, Integer, DECIMAL, DateTime, ForeignKey, func
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import relationship, Mapped

from app.dtos import pack_type_dtos

from app.libs.sql_alchemy_lib import Base

class OrderItemModel(Base):
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    order_id = Column(CHAR(36), ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(CHAR(36), ForeignKey("products.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("pack_types.id"), nullable=True, index=True)
    quantity = Column(Integer, nullable=False)
    price_per_item = Column(DECIMAL(10, 2), nullable=False)
    total_price = Column(DECIMAL(10, 2), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    products: Mapped["ProductModel"] = relationship(
        "ProductModel",
        back_populates="",
    )

    pack_type: Mapped["PackTypeModel"] = relationship(
        "PackTypeModel", 
        back_populates="", 
    )

    order: Mapped[list["OrderModel"]] = relationship(
        "OrderModel", 
        back_populates="order_items", 
        lazy="selectin"
    )
    
    def __repr__(self):
        return f"<OrderItem(id={self.id}, quantity={self.quantity}, price_per_item={self.price_per_item}, product_id='{self.product_id}', order_id='{self.order_id}')>"
    
    @property
    def product_name(self) -> str:
        from app.models.product_model import ProductModel
        products_model: ProductModel = self.products
        return products_model.name if products_model else ""
    
    @property
    def product_price(self):
        if self.pack_type and self.pack_type.price is not None:
            return self.pack_type.price
        return self.products.price if self.products else 0
    
    @property
    def variant_product(self):
        return self.pack_type.variant if self.pack_type else 0

    @property
    def variant_discount(self):
        return self.pack_type.discount if self.pack_type else 0

    @staticmethod
    def _normalize_image_url(url: str | None) -> str | None:
        if not url:
            return None
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

    @property
    def variant_image(self) -> Optional[str]:
        return self._normalize_image_url(self.pack_type.img if self.pack_type else None)

    @property
    def product_image(self) -> Optional[str]:
        product = self.products
        product_images = getattr(product, "product_images", None) if product else None
        if not product_images:
            return None

        sorted_images = sorted(
            product_images,
            key=lambda image: (
                0 if getattr(image, "is_primary", False) else 1,
                getattr(image, "sort_order", 0) or 0,
                getattr(image, "id", 0) or 0,
            ),
        )
        return self._normalize_image_url(sorted_images[0].url if sorted_images else None)

    @property
    def image(self) -> Optional[str]:
        return self.variant_image or self.product_image

    @property
    def promo(self):
        return float(self.pack_type.discount_amount) if self.pack_type and self.pack_type.discount_amount else 0

    @property
    def variant_info(self) -> Optional[Dict[str, Any]]:
        if not self.pack_type:
            return None

        variant = self.pack_type
        return pack_type_dtos.VariantProductCartDto(
            id=variant.id,
            variant=variant.variant,
            name=variant.name,
            img=variant.img,
            price=float(variant.base_price),
            discount=variant.discount,
            discounted_price=float(variant.discounted_price),
        ).model_dump()
