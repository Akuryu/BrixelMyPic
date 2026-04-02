
from __future__ import annotations

import io
import math
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image

from app.core_vendor.lego_mosaic_pro.cli import DEFAULT_CATALOG, DEFAULT_OWNED, DEFAULT_PALETTE, PIECE_CHOICES
from app.core_vendor.lego_mosaic_pro.core import MosaicConfig, generate_mosaic

BOOL_TRUE = {"1", "true", "on", "yes", "y"}
RESIZE_MODE_MAP = {"contain": "fit", "cover": "fill", "stretch": "stretch"}
DEFAULT_PART_NAME = PIECE_CHOICES["tile_1x1_square"]


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
    if piece_type not in PIECE_CHOICES:
        raise ValueError(f"piece_type non supportato: {piece_type}")
    max_colors = _parse_optional_int(params.get("max_colors"))
    resize_mode = str(params.get("resize_mode") or "contain")
    crop_mode = RESIZE_MODE_MAP.get(resize_mode, "fit")
    panel_rounding = str(params.get("panel_rounding") or "nearest")
    if panel_rounding not in {"nearest", "up", "down", "none"}:
        panel_rounding = "nearest"
    rounded_width = _round_dim(width, panel_size, panel_rounding)
    rounded_height = _round_dim(height, panel_size, panel_rounding) if height else None
    return {
        "width": rounded_width,
        "height": rounded_height,
        "piece_type": piece_type,
        "part_name": PIECE_CHOICES.get(piece_type, DEFAULT_PART_NAME),
        "max_colors": max_colors,
        "resize_mode": resize_mode,
        "crop_mode": crop_mode,
        "panel_rounding": panel_rounding,
        "dither": _parse_bool(params.get("dither"), True),
        "generate_pdf": _parse_bool(params.get("generate_pdf"), True),
        "generate_stud_preview": _parse_bool(params.get("generate_stud_preview"), True),
        "piece_aware_palette": _parse_bool(params.get("piece_aware_palette"), True),
        "original_width": width,
        "original_height": height,
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


def _run_core(image_bytes: bytes, params: dict[str, Any], output_dir: Path) -> tuple[dict[str, str], dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_input = output_dir / "input_image.png"
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.convert("RGB").save(temp_input, format="PNG")
    normalized = normalize_params(params)
    config = build_config_from_params(params)
    result = generate_mosaic(temp_input, DEFAULT_PALETTE, output_dir, config)
    return result, normalized


def generate_preview_from_bytes(image_bytes: bytes, params: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="leobrick_preview_") as tmp_dir:
        out_dir = Path(tmp_dir) / "output"
        result, normalized = _run_core(image_bytes, params, out_dir)
        preview_path = Path(result["preview_stud"] or result["preview_pixel"])
        preview_bytes = preview_path.read_bytes()
        normalized.update({
            "palette_size": int(result.get("palette_size") or 0),
            "width": int(result.get("width") or normalized["width"]),
            "height": int(result.get("height") or (normalized.get("height") or 0)),
            "preview_file": preview_path.name,
        })
        return preview_bytes, normalized


def generate_package_from_bytes(image_bytes: bytes, params: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    result, normalized = _run_core(image_bytes, params, output_dir)
    zip_path = output_dir / "output.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in output_dir.rglob("*"):
            if path.name == "output.zip" or not path.is_file():
                continue
            zf.write(path, arcname=path.relative_to(output_dir))
    normalized.update({
        "palette_size": int(result.get("palette_size") or 0),
        "width": int(result.get("width") or normalized["width"]),
        "height": int(result.get("height") or (normalized.get("height") or 0)),
        "zip_path": str(zip_path),
        "files": result,
    })
    return normalized
