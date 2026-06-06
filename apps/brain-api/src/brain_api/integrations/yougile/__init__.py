"""YouGile board integration (REST API v2), per-team / multi-tenant.

Thin HTTP client (client.py) + rate limiter (ratelimit.py) + mapping repo
(mappings.py). Business logic lives in the board adapter and discovery use-cases.
"""

from brain_api.integrations.yougile.client import DEFAULT_BASE_URL, YouGileClient
from brain_api.integrations.yougile.exceptions import (
    YouGileAuthError,
    YouGileConfigError,
    YouGileError,
    YouGileHTTPError,
    YouGileNotFound,
    YouGilePermissionError,
    YouGileServerError,
)
from brain_api.integrations.yougile.mappings import YouGileMappingRepo
from brain_api.integrations.yougile.ratelimit import TokenBucket, bucket_for

__all__ = [
    "YouGileClient",
    "DEFAULT_BASE_URL",
    "YouGileError",
    "YouGileConfigError",
    "YouGileHTTPError",
    "YouGileAuthError",
    "YouGilePermissionError",
    "YouGileNotFound",
    "YouGileServerError",
    "YouGileMappingRepo",
    "TokenBucket",
    "bucket_for",
]
