import logging

from app.libs.redis_config import redis_client

logger = logging.getLogger(__name__)


def invalidate_user_address_cache(user_id: str) -> None:
    """Best-effort invalidation for cached shipment-address responses.

    The owner-address endpoint stores its single-address cache at the exact key
    ``origin_address:{user_id}``, while list endpoints use suffixed keys. Delete
    both shapes so checkout never keeps showing a stale store sender address
    after the database row is updated.
    """
    if not redis_client:
        return

    exact_keys = (f"origin_address:{user_id}",)
    patterns = (
        f"origin_address:{user_id}:*",
        f"origin_address:v2:{user_id}:*",
    )
    try:
        redis_client.delete(*exact_keys)
        for pattern in patterns:
            for key in redis_client.scan_iter(pattern):
                redis_client.delete(key)
    except Exception as cache_error:
        logger.warning(
            "Failed to invalidate shipping address cache for user %s: %s",
            user_id,
            cache_error,
        )
