import os
import pytest
from app.config import Settings


def test_settings_loads_defaults():
    os.environ.setdefault("KALSHI_API_KEY_ID", "test_key")
    os.environ.setdefault("KALSHI_PRIVATE_KEY_PATH", "./secrets/test.pem")
    s = Settings()
    assert s.db_path == "./data/tennis_odds.db"
    assert s.fetch_cron_hour == 3
    assert s.fetch_cron_minute == 0
    assert s.sackmann_data_dir == "./data/sackmann"


def test_settings_loads_env_overrides():
    os.environ["DB_PATH"] = "/tmp/test.db"
    os.environ["FETCH_CRON_HOUR"] = "5"
    os.environ.setdefault("KALSHI_API_KEY_ID", "test_key")
    os.environ.setdefault("KALSHI_PRIVATE_KEY_PATH", "./secrets/test.pem")
    s = Settings()
    assert s.db_path == "/tmp/test.db"
    assert s.fetch_cron_hour == 5
    # Cleanup
    del os.environ["DB_PATH"]
    del os.environ["FETCH_CRON_HOUR"]
