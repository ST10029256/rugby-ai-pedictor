from __future__ import annotations

import os
from pydantic import BaseModel
from dotenv import load_dotenv


class AppConfig(BaseModel):
    api_key: str
    base_url: str = "https://www.thesportsdb.com/api/v1/json"
    rate_limit_rpm: int = 30


def load_config() -> AppConfig:
    # Load .env if present
    load_dotenv()

    api_key = os.getenv("THESPORTSDB_API_KEY", "123")
    base_url = os.getenv("THESPORTSDB_BASE_URL", "https://www.thesportsdb.com/api/v1/json")
    rate_limit_rpm = int(os.getenv("RATE_LIMIT_RPM", "30"))

    return AppConfig(api_key=api_key, base_url=base_url, rate_limit_rpm=rate_limit_rpm)
