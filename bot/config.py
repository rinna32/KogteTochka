from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    master_id: int
    admin_id: int = 0
    database_url: str
    tz: str = "Europe/Moscow"

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)


settings = Settings()
