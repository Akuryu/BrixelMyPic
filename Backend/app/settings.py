from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel

class Settings(BaseModel):
    app_name: str = "LeoBrick API"
    storage_root: Path = Path("storage")
    max_upload_bytes: int = 15 * 1024 * 1024
    panel_size: int = 16

    internal_api_key: str = "SUPER_SECRET_KEY"
    telegram_bot_token: str = "8652550499:AAHcDE0lx0QadSC5EfbL4E3H7j1TIOjuW6Y"
    telegram_allowed_users: list[int] = [1779627639]


    @property
    def jobs_root(self) -> Path:
        return self.storage_root / "jobs"

    @property
    def tmp_root(self) -> Path:
        return self.storage_root / "tmp"


settings = Settings()
