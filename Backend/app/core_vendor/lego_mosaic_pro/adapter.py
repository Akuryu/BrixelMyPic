
from __future__ import annotations

import io
import math
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image

from .cli import DEFAULT_CATALOG, DEFAULT_OWNED, DEFAULT_PALETTE, PIECE_CHOICES
from .core import MosaicConfig, generate_mosaic

BOOL_TRUE = {"1", "true", "on", "yes", "y"}
RESIZE_MODE_MAP = {"contain": "fit", "cover": "fill", "stretch": "stretch"}


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in BOOL_TRUE


def _parse_optional_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    return int(value)


def _round_dim(value: int, panel_size: int, mode: str) -> int:
    if mode == "none":
        return max(1, value)
    ratio = value / panel_size
    if mode == "up":
        return max(panel_size, math.ceil(ratio) * panel_size)
    if mode == "down":
        return max(panel_size, math.floor(ratio) * panel_size)
    return max(panel_size, round(ratio) * panel_size)


def normalize_params(params: dict[str, Any], panel_size: int = 16) -> dict[str, Any]:
    width = int(params.get("width") or 128)
    height = _parse_optional_int(params.get("height"))
    piece_type = str(params.get("piece_type") or "tile_1x1_square")
    max_colors = _parse_optional_int(params.get("max_colors"))
    resize_mode = str(params.get("resize_mode") or "contain")
    crop_mode = RESIZE_MODE_MAP.get(resize_mode, "fit")
    panel_rounding = str(params.get("panel_rounding") or "nearest")
    return {
        "width": _round_dim(width, panel_size, panel_rounding),
        "height": _round_dim(height, panel_size, panel_rounding) if height else None,
        "piece_type": piece_type,
        "part_name": PIECE_CHOICES[piece_type],
        "max_colors": max_colors,
        "resize_mode": resize_mode,
        "crop_mode": crop_mode,
        "panel_rounding": panel_rounding,
        "dither": _parse_bool(params.get("dither"), True),
        "generate_pdf": _parse_bool(params.get("generate_pdf"), True),
        "generate_stud_preview": _parse_bool(params.get("generate_stud_preview"), True),
        "piece_aware_palette": _parse_bool(params.get("piece_aware_palette"), True),
    }


def build_config_from_params(params: dict[str, Any], panel_size: int = 16) -> MosaicConfig:
    normalized = normalize_params(params, panel_size=panel_size)
    return MosaicConfig(
        width=normalized["width"],
        height=normalized["height"],
        panel_size=panel_size,
        enforce_panel_multiple=False,
        dither=normalized["dither"],
        crop_mode=normalized["crop_mode"],
        generate_pdf=normalized["generate_pdf"],
        generate_stud_preview=normalized["generate_stud_preview"],
        piece_type=normalized["piece_type"],
        part_name=normalized["part_name"],
        catalog_path=str(DEFAULT_CATALOG),
        owned_inventory_path=str(DEFAULT_OWNED),
        piece_aware_palette=normalized["piece_aware_palette"],
        max_colors=normalized["max_colors"],
    )


def generate_preview_from_bytes(image_bytes: bytes, params: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="lego_preview_") as tmp_dir:
        output_dir = Path(tmp_dir) / "output"
        input_path = Path(tmp_dir) / "input.png"
        Image.open(io.BytesIO(image_bytes)).convert("RGB").save(input_path, format="PNG")
        result = generate_mosaic(input_path, DEFAULT_PALETTE, output_dir, build_config_from_params(params))
        preview_path = Path(result["preview_stud"] or result["preview_pixel"])
        meta = normalize_params(params)
        meta.update({"width": int(result["width"]), "height": int(result["height"]), "palette_size": int(result["palette_size"])})
        return preview_path.read_bytes(), meta


def generate_package_from_bytes(image_bytes: bytes, params: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = output_dir / "input.png"
    Image.open(io.BytesIO(image_bytes)).convert("RGB").save(input_path, format="PNG")
    result = generate_mosaic(input_path, DEFAULT_PALETTE, output_dir, build_config_from_params(params))
    zip_path = output_dir / "output.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in output_dir.rglob("*"):
            if path.name == "output.zip" or not path.is_file():
                continue
            zf.write(path, arcname=path.relative_to(output_dir))
    meta = normalize_params(params)
    meta.update({"width": int(result["width"]), "height": int(result["height"]), "palette_size": int(result["palette_size"]), "files": result, "zip_path": str(zip_path)})
    return meta
