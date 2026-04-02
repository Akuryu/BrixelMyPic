
from __future__ import annotations
import json, secrets, string, time
from pathlib import Path
from typing import Any


def generate_public_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "LEO-" + "".join(secrets.choice(alphabet) for _ in range(6))


def generate_redeem_token() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "RDM-" + "".join(secrets.choice(alphabet) for _ in range(10))


def utc_timestamp() -> float:
    return time.time()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
