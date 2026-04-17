# backend/app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Kalshi API
    kalshi_api_key_id: str = ""
    kalshi_private_key_path: str = "./secrets/kalshi_private.pem"

    # Database
    db_path: str = "./data/tennis_odds.db"

    # Scheduler
    fetch_cron_hour: int = 3
    fetch_cron_minute: int = 0

    # Sackmann
    sackmann_data_dir: str = "./data/sackmann"

    # OpenAI
    openai_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
