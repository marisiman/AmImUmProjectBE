import logging

from app.libs.redis_config import redis_client

logger = logging.getLogger(__name__)


def invalidate_product_cache(product_id: str | None = None) -> None:
    if not redis_client:
        return
    patterns = ["products:*", "product:*"]
    if product_id:
        patterns.append(f"product:{product_id}")
    try:
        for pattern in patterns:
            for key in redis_client.scan_iter(pattern):
                redis_client.delete(key)
    except Exception as exc:
        logger.warning("product_cache_invalidation_failed product_id=%s error=%s", product_id, exc)
