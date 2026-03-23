from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Telegram
    bot_token: str = Field(..., env="BOT_TOKEN")

    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # Redis
    redis_url: str = Field(..., env="REDIS_URL")

    # RabbitMQ
    rabbitmq_url: str = Field(..., env="RABBITMQ_URL")

    # Security
    encryption_key: str = Field(..., env="ENCRYPTION_KEY")

    # Captcha
    anticaptcha_key: str = Field("", env="ANTICAPTCHA_KEY")

    # Misc
    log_level: str = Field("INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"


settings = Settings()
