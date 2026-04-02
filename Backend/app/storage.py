
from __future__ import annotations
from pathlib import Path
from .settings import settings
from .utils import read_json, write_json


class Storage:
    def __init__(self, jobs_root: Path | None = None):
        self.jobs_root = jobs_root or settings.jobs_root
        self.jobs_root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, code: str) -> Path:
        return self.jobs_root / code

    def ensure_job_dir(self, code: str) -> Path:
        path = self.job_dir(code)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def metadata_path(self, code: str) -> Path:
        return self.job_dir(code) / "metadata.json"

    def zip_path(self, code: str) -> Path:
        return self.job_dir(code) / "output.zip"

    def save_metadata(self, code: str, payload: dict):
        write_json(self.metadata_path(code), payload)

    def load_metadata(self, code: str) -> dict:
        return read_json(self.metadata_path(code))

    def find_by_token(self, token: str) -> tuple[str, dict] | tuple[None, None]:
        for job_dir in self.jobs_root.iterdir():
            if not job_dir.is_dir():
                continue
            meta_path = job_dir / "metadata.json"
            if not meta_path.exists():
                continue
            meta = read_json(meta_path)
            if meta.get("redeem_token") == token:
                return job_dir.name, meta
        return None, None
