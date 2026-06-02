from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    internal_api_token: str = "dev-internal-token"


def get_settings() -> Settings:
    return Settings(
        internal_api_token=os.getenv("INTERNAL_API_TOKEN", "dev-internal-token"),
    )

