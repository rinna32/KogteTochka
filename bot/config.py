from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    master_id: int = 0
    admin_id: int = 0
    database_url: str
    tz: str = "Europe/Moscow"
    # Контакты, которые клиентка видит после записи, например @nails_master
    master_contact: str = ""
    admin_contact: str = ""

    @field_validator("master_id", "admin_id", mode="before")
    @classmethod
    def empty_id(cls, value: object) -> object:
        # пустой ID в .env — такого человека нет (например, на время теста глазами клиентки)
        return 0 if value == "" else value

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def staff_ids(self) -> set[int]:
        """Кто может управлять ботом: мастер и админ."""
        return {i for i in (self.master_id, self.admin_id) if i}

    def panel_name(self, user_id: int) -> str | None:
        """Чьё меню управления видит человек: «мастера», «админа» или никакое."""
        if self.master_id and user_id == self.master_id:
            return "мастера"
        if self.admin_id and user_id == self.admin_id:
            return "админа"
        return None


settings = Settings()
