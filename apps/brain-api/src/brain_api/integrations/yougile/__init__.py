"""YouGile board integration (REST API v2).

Real integration when YOUGILE_ENABLED=true and credentials are present;
honest "disabled" fallback otherwise — the local board keeps working.
"""

from brain_api.integrations.yougile.client import YouGileClient
from brain_api.integrations.yougile.exceptions import (
    YouGileConfigError,
    YouGileError,
    YouGileHTTPError,
)
from brain_api.integrations.yougile.models import (
    SyncResult,
    YouGileConfig,
    YouGileHealth,
)
from brain_api.integrations.yougile.service import (
    YouGileBoardService,
    get_yougile_service,
    reset_yougile_service,
    set_yougile_service,
)

__all__ = [
    "YouGileClient",
    "YouGileError",
    "YouGileConfigError",
    "YouGileHTTPError",
    "YouGileConfig",
    "YouGileHealth",
    "SyncResult",
    "YouGileBoardService",
    "get_yougile_service",
    "set_yougile_service",
    "reset_yougile_service",
]
