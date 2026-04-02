
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "LeoBrick API"
    storage_root: Path = Path("storage")
    max_upload_bytes: int = 15 * 1024 * 1024
    panel_size: int = 16

    @property
    def jobs_root(self) -> Path:
        return self.storage_root / "jobs"


settings = Settings()
