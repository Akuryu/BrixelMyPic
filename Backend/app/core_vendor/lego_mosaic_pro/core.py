from __future__ import annotations

import csv
import json
import math
import statistics
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageEnhance


@dataclass(frozen=True)
class PaletteColor:
    name: str
    rgb: tuple[int, int, int]
    material: str = "solid"
    lego_id: str | None = None
    bricklink_id: str | None = None
    ldraw_id: str | None = None
    current: bool = True

    @property
    def hex(self) -> str:
        return "#{:02X}{:02X}{:02X}".format(*self.rgb)


@dataclass(frozen=True)
class CatalogEntry:
    piece_type: str
    piece_name: str
    part_id: str
    color_name: str
    available: bool
    avg_price_eur: float
    lego_color_id: str | None = None
    bricklink_color_id: str | None = None
    rgb: str | None = None


@dataclass
class MosaicConfig:
    width: int
    height: int | None = None
    panel_size: int = 16
    current_only: bool = True
    include_materials: tuple[str, ...] = ("solid",)
    exclude_materials: tuple[str, ...] = ("ink",)
    dither: bool = True
    crop_mode: str = "fit"
    contrast: float = 1.08
    saturation: float = 0.95
    sharpen: float = 1.05
    stud_preview_scale: int = 24
    pixel_preview_scale: int = 24
    enforce_panel_multiple: bool = True
    generate_pdf: bool = True
    generate_stud_preview: bool = True
    piece_type: str = "tile_1x1_square"
    part_name: str = "Tile 1x1"
    catalog_path: str | None = None
    owned_inventory_path: str | None = None
    piece_aware_palette: bool = True
    max_colors: int | None = None
    generate_wanted_list: bool = True
    generate_overview: bool = True
    generate_json_report: bool = True


# ---------- color math ----------

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Valore RGB non valido: {value}")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def srgb_to_linear(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = [srgb_to_linear(v) for v in rgb]
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    x /= 0.95047
    y /= 1.00000
    z /= 1.08883

    def f(t: float) -> float:
        delta = 6 / 29
        return t ** (1 / 3) if t > delta**3 else (t / (3 * delta**2)) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def lab_distance_sq(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


# ---------- palette and catalog ----------

def load_palette(
    xml_path: str | Path,
    include_materials: Sequence[str] | None = None,
    exclude_materials: Sequence[str] | None = None,
    current_only: bool = False,
) -> list[PaletteColor]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    include = {m.lower() for m in include_materials} if include_materials else None
    exclude = {m.lower() for m in exclude_materials} if exclude_materials else set()
    palette: list[PaletteColor] = []
    for node in root.findall("color"):
        material = (node.get("material") or "solid").lower()
        current = (node.get("current") or "true").lower() == "true"
        if include is not None and material not in include:
            continue
        if material in exclude:
            continue
        if current_only and not current:
            continue
        name = node.get("name")
        rgb_hex = node.get("rgb")
        if not name or not rgb_hex:
            continue
        palette.append(
            PaletteColor(
                name=name,
                rgb=hex_to_rgb(rgb_hex),
                material=material,
                lego_id=node.get("lego_id"),
                bricklink_id=node.get("bricklink_id"),
                ldraw_id=node.get("ldraw_id"),
                current=current,
            )
        )
    if not palette:
        raise ValueError("La palette risultante è vuota.")
    return palette


def load_catalog(path: str | Path, piece_type: str) -> dict[str, CatalogEntry]:
    rows: dict[str, CatalogEntry] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            if row["piece_type"] != piece_type:
                continue
            rows[row["color_name"]] = CatalogEntry(
                piece_type=row["piece_type"],
                piece_name=row["piece_name"],
                part_id=row["part_id"],
                color_name=row["color_name"],
                available=(row["available"].lower() == "true"),
                avg_price_eur=float(row["avg_price_eur"]),
                lego_color_id=row.get("lego_color_id") or None,
                bricklink_color_id=row.get("bricklink_color_id") or None,
                rgb=row.get("rgb") or None,
            )
    if not rows:
        raise ValueError(f"Catalogo vuoto per piece_type={piece_type}")
    return rows


def load_owned_inventory(path: str | Path, piece_type: str) -> dict[str, int]:
    owned: dict[str, int] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            if row["piece_type"] != piece_type:
                continue
            owned[row["color_name"]] = owned.get(row["color_name"], 0) + int(row["owned_qty"])
    return owned


def palette_stats(palette: Sequence[PaletteColor]) -> dict[str, object]:
    materials = Counter(p.material for p in palette)
    return {"colors": len(palette), "materials": dict(sorted(materials.items()))}


# ---------- image prep ----------

def enforce_multiple(value: int, base: int) -> int:
    return max(base, int(round(value / base)) * base)




def validate_config(config: MosaicConfig) -> None:
    if config.width <= 0:
        raise ValueError("La larghezza deve essere maggiore di zero.")
    if config.height is not None and config.height <= 0:
        raise ValueError("L'altezza deve essere maggiore di zero quando viene specificata.")
    if config.panel_size <= 0:
        raise ValueError("La dimensione del pannello deve essere maggiore di zero.")
    if config.pixel_preview_scale <= 0 or config.stud_preview_scale <= 0:
        raise ValueError("Le scale di preview devono essere maggiori di zero.")
    if config.max_colors is not None and config.max_colors <= 0:
        raise ValueError("max_colors deve essere maggiore di zero, oppure None.")
    if config.crop_mode not in {"fit", "fill", "stretch"}:
        raise ValueError("crop_mode deve essere fit, fill oppure stretch.")

def infer_height_preserving_aspect(image: Image.Image, width: int) -> int:
    aspect = image.height / image.width
    return max(1, round(width * aspect))


def fit_or_fill(image: Image.Image, width: int, height: int, mode: str) -> Image.Image:
    image = image.convert("RGB")
    if mode == "stretch":
        return image.resize((width, height), Image.Resampling.LANCZOS)
    src_ratio = image.width / image.height
    dst_ratio = width / height
    if (mode == "fill" and src_ratio > dst_ratio) or (mode == "fit" and src_ratio < dst_ratio):
        new_h = height
        new_w = round(new_h * src_ratio)
    else:
        new_w = width
        new_h = round(new_w / src_ratio)
    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    if mode == "fill":
        left = max(0, (new_w - width) // 2)
        top = max(0, (new_h - height) // 2)
        return resized.crop((left, top, left + width, top + height))
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    left = (width - new_w) // 2
    top = (height - new_h) // 2
    canvas.paste(resized, (left, top))
    return canvas


def preprocess_image(image: Image.Image, contrast: float, saturation: float, sharpen: float) -> Image.Image:
    image = ImageEnhance.Contrast(image).enhance(contrast)
    image = ImageEnhance.Color(image).enhance(saturation)
    image = ImageEnhance.Sharpness(image).enhance(sharpen)
    return image


# ---------- quantization ----------

def nearest_palette_color(rgb: tuple[int, int, int], palette_lab: Sequence[tuple[PaletteColor, tuple[float, float, float]]]) -> PaletteColor:
    lab = rgb_to_lab(rgb)
    return min(palette_lab, key=lambda item: lab_distance_sq(item[1], lab))[0]


def floyd_steinberg_dither(image: Image.Image, palette: Sequence[PaletteColor]) -> Image.Image:
    img = image.convert("RGB")
    pixels = [[list(img.getpixel((x, y))) for x in range(img.width)] for y in range(img.height)]
    out = Image.new("RGB", img.size)
    palette_lab = [(p, rgb_to_lab(p.rgb)) for p in palette]
    for y in range(img.height):
        for x in range(img.width):
            old = tuple(max(0, min(255, int(round(v)))) for v in pixels[y][x])
            best = nearest_palette_color(old, palette_lab)
            new = best.rgb
            out.putpixel((x, y), new)
            err = [old[i] - new[i] for i in range(3)]

            def add(nx: int, ny: int, factor: float) -> None:
                if 0 <= nx < img.width and 0 <= ny < img.height:
                    for i in range(3):
                        pixels[ny][nx][i] += err[i] * factor

            add(x + 1, y, 7 / 16)
            add(x - 1, y + 1, 3 / 16)
            add(x, y + 1, 5 / 16)
            add(x + 1, y + 1, 1 / 16)
    return out


def quantize_to_palette(image: Image.Image, palette: Sequence[PaletteColor]) -> tuple[Image.Image, list[list[PaletteColor]]]:
    img = image.convert("RGB")
    out = Image.new("RGB", img.size)
    palette_lab = [(p, rgb_to_lab(p.rgb)) for p in palette]
    grid: list[list[PaletteColor]] = []
    for y in range(img.height):
        row: list[PaletteColor] = []
        for x in range(img.width):
            best = nearest_palette_color(img.getpixel((x, y)), palette_lab)
            out.putpixel((x, y), best.rgb)
            row.append(best)
        grid.append(row)
    return out, grid


def reduce_palette_to_top_colors(grid: Sequence[Sequence[PaletteColor]], max_colors: int) -> tuple[list[PaletteColor], Counter[PaletteColor]]:
    counter: Counter[PaletteColor] = Counter()
    for row in grid:
        counter.update(row)
    keep = [color for color, _ in counter.most_common(max_colors)]
    return keep, counter


# ---------- previews ----------

def save_pixel_preview(image: Image.Image, out_path: str | Path, scale: int) -> None:
    image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST).save(out_path)


def mix_with_white(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(min(255, int(round(c + (255 - c) * factor))) for c in rgb)


def mix_with_black(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, int(round(c * (1 - factor)))) for c in rgb)


def render_stud_preview(grid: Sequence[Sequence[PaletteColor]], cell: int = 24, gap: int = 2) -> Image.Image:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    img = Image.new("RGB", (cols * cell, rows * cell), (248, 248, 248))
    draw = ImageDraw.Draw(img)
    for y, row in enumerate(grid):
        for x, color in enumerate(row):
            left = x * cell
            top = y * cell
            right = left + cell - 1
            bottom = top + cell - 1
            draw.rectangle((left, top, right, bottom), fill=color.rgb)
            inset = max(2, cell // 6)
            draw.ellipse(
                (left + inset, top + inset, right - inset, bottom - inset),
                fill=mix_with_white(color.rgb, 0.18),
                outline=mix_with_black(color.rgb, 0.18),
                width=max(1, cell // 18),
            )
            if gap:
                draw.rectangle((left, top, right, bottom), outline=(210, 210, 210), width=1)
    return img


def render_overview(grid: Sequence[Sequence[PaletteColor]], panel_size: int, cell: int = 8) -> Image.Image:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    margin = 40
    img = Image.new("RGB", (cols * cell + margin * 2, rows * cell + margin * 2), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for y, row in enumerate(grid):
        for x, color in enumerate(row):
            left = margin + x * cell
            top = margin + y * cell
            draw.rectangle((left, top, left + cell, top + cell), fill=color.rgb)
    for x in range(0, cols + 1, panel_size):
        xx = margin + x * cell
        draw.line((xx, margin, xx, margin + rows * cell), fill=(30, 30, 30), width=2)
    for y in range(0, rows + 1, panel_size):
        yy = margin + y * cell
        draw.line((margin, yy, margin + cols * cell, yy), fill=(30, 30, 30), width=2)
    for px in range(math.ceil(cols / panel_size)):
        for py in range(math.ceil(rows / panel_size)):
            cx = margin + (px * panel_size + panel_size / 2) * cell
            cy = margin + (py * panel_size + panel_size / 2) * cell
            draw.text((cx - 12, cy - 7), f"{py+1},{px+1}", fill=(0, 0, 0))
    return img


# ---------- exports ----------

def build_inventory(grid: Sequence[Sequence[PaletteColor]]) -> list[tuple[PaletteColor, int]]:
    counter: Counter[PaletteColor] = Counter()
    for row in grid:
        counter.update(row)
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].name))


def export_inventory_csv(grid: Sequence[Sequence[PaletteColor]], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["name", "count", "rgb", "material", "lego_id", "bricklink_id", "ldraw_id"])
        for color, count in build_inventory(grid):
            writer.writerow([color.name, count, color.hex, color.material, color.lego_id or "", color.bricklink_id or "", color.ldraw_id or ""])


def export_grid_csv(grid: Sequence[Sequence[PaletteColor]], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        header = ["row"] + [f"x{x+1}" for x in range(len(grid[0]))]
        writer.writerow(header)
        for y, row in enumerate(grid, start=1):
            writer.writerow([f"y{y}"] + [c.name for c in row])


def split_panels(grid: Sequence[Sequence[PaletteColor]], panel_size: int) -> list[tuple[int, int, list[list[PaletteColor]]]]:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    panels = []
    for top in range(0, rows, panel_size):
        for left in range(0, cols, panel_size):
            panels.append((left // panel_size, top // panel_size, [list(row[left:left + panel_size]) for row in grid[top:top + panel_size]]))
    return panels


def render_instruction_panel(subgrid: Sequence[Sequence[PaletteColor]], px: int, py: int, cell: int = 40) -> Image.Image:
    rows = len(subgrid)
    cols = len(subgrid[0]) if rows else 0
    margin_top = 50
    margin_left = 50
    img = Image.new("RGB", (margin_left + cols * cell + 2, margin_top + rows * cell + 2), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 12), f"Panel {py+1},{px+1}", fill=(0, 0, 0))
    for x in range(cols):
        draw.text((margin_left + x * cell + cell // 3, 18), str(x + 1), fill=(0, 0, 0))
    for y in range(rows):
        draw.text((15, margin_top + y * cell + cell // 3), str(y + 1), fill=(0, 0, 0))
    for y, row in enumerate(subgrid):
        for x, color in enumerate(row):
            left = margin_left + x * cell
            top = margin_top + y * cell
            draw.rectangle((left, top, left + cell, top + cell), fill=color.rgb, outline=(140, 140, 140), width=1)
            label = color.name[:3].upper()
            text_fill = (0, 0, 0) if sum(color.rgb) > 360 else (255, 255, 255)
            draw.text((left + 6, top + 10), label, fill=text_fill)
    return img


def export_panels(grid: Sequence[Sequence[PaletteColor]], instructions_dir: str | Path, panel_size: int) -> list[Path]:
    instructions_dir = Path(instructions_dir)
    instructions_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for px, py, subgrid in split_panels(grid, panel_size):
        out = instructions_dir / f"panel_{py+1:02d}_{px+1:02d}.png"
        render_instruction_panel(subgrid, px, py).save(out)
        paths.append(out)
    return paths


def export_legend_csv(grid: Sequence[Sequence[PaletteColor]], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["abbr", "name", "rgb", "lego_id", "bricklink_id"])
        for color, _ in build_inventory(grid):
            writer.writerow([color.name[:3].upper(), color.name, color.hex, color.lego_id or "", color.bricklink_id or ""])


def compute_purchase_plan(grid: Sequence[Sequence[PaletteColor]], catalog: dict[str, CatalogEntry], owned: dict[str, int] | None = None) -> list[dict[str, object]]:
    owned = owned or {}
    plan = []
    for color, required in build_inventory(grid):
        entry = catalog.get(color.name)
        available = bool(entry and entry.available)
        avg_price = entry.avg_price_eur if entry else 0.0
        owned_qty = owned.get(color.name, 0)
        missing_qty = max(0, required - owned_qty)
        est_cost = missing_qty * avg_price if available else 0.0
        plan.append(
            {
                "color_name": color.name,
                "required_qty": required,
                "owned_qty": owned_qty,
                "missing_qty": missing_qty,
                "available_for_piece": available,
                "avg_price_eur": round(avg_price, 3),
                "estimated_cost_eur": round(est_cost, 2),
                "part_id": entry.part_id if entry else "",
                "piece_name": entry.piece_name if entry else "",
                "lego_color_id": entry.lego_color_id if entry else "",
                "bricklink_color_id": entry.bricklink_color_id if entry else "",
            }
        )
    return plan


def export_purchase_plan_csv(plan: Sequence[dict[str, object]], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "color_name",
                "required_qty",
                "owned_qty",
                "missing_qty",
                "available_for_piece",
                "avg_price_eur",
                "estimated_cost_eur",
                "piece_name",
                "part_id",
                "lego_color_id",
                "bricklink_color_id",
            ],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(plan)


def export_compatibility_csv(plan: Sequence[dict[str, object]], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["color_name", "compatible", "required_qty", "piece_name", "part_id"])
        for row in plan:
            writer.writerow([row["color_name"], "yes" if row["available_for_piece"] else "no", row["required_qty"], row["piece_name"], row["part_id"]])


def build_panel_inventory(subgrid: Sequence[Sequence[PaletteColor]]) -> list[tuple[str, int]]:
    counter = Counter(c.name for row in subgrid for c in row)
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


def export_panel_inventory_csv(grid: Sequence[Sequence[PaletteColor]], panel_size: int, path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["panel_row", "panel_col", "color_name", "count"])
        for px, py, subgrid in split_panels(grid, panel_size):
            for color_name, count in build_panel_inventory(subgrid):
                writer.writerow([py + 1, px + 1, color_name, count])


def export_cost_summary_txt(plan: Sequence[dict[str, object]], path: str | Path, part_name: str) -> None:
    total_required = sum(int(r["required_qty"]) for r in plan)
    total_missing = sum(int(r["missing_qty"]) for r in plan)
    total_cost = sum(float(r["estimated_cost_eur"]) for r in plan)
    unavailable = [r for r in plan if not r["available_for_piece"]]
    prices = [float(r["avg_price_eur"]) for r in plan if float(r["avg_price_eur"]) > 0]
    with open(path, "w", encoding="utf-8") as f:
        f.write("LEGO Mosaic Pro - Cost Summary\n")
        f.write(f"Elemento selezionato: {part_name}\n")
        f.write(f"Pezzi richiesti: {total_required}\n")
        f.write(f"Pezzi da acquistare: {total_missing}\n")
        f.write(f"Stima costo: EUR {total_cost:.2f}\n")
        if prices:
            f.write(f"Prezzo medio colore: EUR {statistics.mean(prices):.3f}\n")
        f.write(f"Colori non compatibili con questo pezzo: {len(unavailable)}\n")
        if unavailable:
            f.write("Elenco incompatibili:\n")
            for row in unavailable:
                f.write(f"- {row['color_name']} ({row['required_qty']} pcs)\n")


def export_summary_txt(grid: Sequence[Sequence[PaletteColor]], path: str | Path, panel_size: int, piece_type: str, max_colors: int | None) -> None:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    panels_x = math.ceil(cols / panel_size)
    panels_y = math.ceil(rows / panel_size)
    pieces = sum(count for _, count in build_inventory(grid))
    with open(path, "w", encoding="utf-8") as f:
        f.write("LEGO Mosaic Pro - Summary\n")
        f.write(f"Dimensioni mosaico: {cols} x {rows} stud\n")
        f.write(f"Pannelli: {panels_x} x {panels_y} da {panel_size}x{panel_size}\n")
        f.write(f"Totale pezzi 1x1: {pieces}\n")
        f.write(f"Colori usati: {len(build_inventory(grid))}\n")
        f.write(f"Pezzo target: {piece_type}\n")
        f.write(f"Limite colori: {max_colors if max_colors else 'nessuno'}\n")


def export_wanted_list_xml(plan: Sequence[dict[str, object]], path: str | Path) -> None:
    root = ET.Element("INVENTORY")
    for row in plan:
        qty = int(row["missing_qty"])
        if qty <= 0 or not row["available_for_piece"]:
            continue
        item = ET.SubElement(root, "ITEM")
        ET.SubElement(item, "ITEMTYPE").text = "P"
        ET.SubElement(item, "ITEMID").text = str(row["part_id"])
        ET.SubElement(item, "COLOR").text = str(row.get("bricklink_color_id") or 0)
        ET.SubElement(item, "MINQTY").text = str(qty)
        ET.SubElement(item, "CONDITION").text = "N"
        ET.SubElement(item, "REMARKS").text = str(row["color_name"])
    Path(path).write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")


def export_json_report(report: dict[str, object], path: str | Path) -> None:
    Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def export_instructions_pdf(grid: Sequence[Sequence[PaletteColor]], pdf_path: str | Path, panel_paths: Sequence[Path], panel_size: int, plan: Sequence[dict[str, object]], part_name: str, overview_path: str | Path | None = None) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    pdf_path = str(pdf_path)
    c = canvas.Canvas(pdf_path, pagesize=A4)
    w, h = A4
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    inventory = build_inventory(grid)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2 * cm, h - 2 * cm, "LEGO Mosaic Pro - Istruzioni")
    c.setFont("Helvetica", 11)
    c.drawString(2 * cm, h - 3 * cm, f"Dimensioni: {cols} x {rows} stud")
    c.drawString(2 * cm, h - 3.7 * cm, f"Pannelli: {math.ceil(cols/panel_size)} x {math.ceil(rows/panel_size)} da {panel_size}x{panel_size}")
    c.drawString(2 * cm, h - 4.4 * cm, f"Pezzo scelto: {part_name}")
    c.drawString(2 * cm, h - 5.1 * cm, f"Pezzi totali 1x1: {sum(v for _, v in inventory)}")
    c.drawString(2 * cm, h - 5.8 * cm, f"Stima costo: EUR {sum(float(r['estimated_cost_eur']) for r in plan):.2f}")
    y = h - 7.0 * cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y, "Distinta base e acquisti")
    y -= 0.7 * cm
    c.setFont("Helvetica", 10)
    for row in plan[:28]:
        line = f"- {row['color_name']}: req {row['required_qty']} / buy {row['missing_qty']} / EUR {float(row['estimated_cost_eur']):.2f}"
        if not row["available_for_piece"]:
            line += " (non compatibile)"
        c.drawString(2 * cm, y, line)
        y -= 0.5 * cm
        if y < 2 * cm:
            c.showPage()
            y = h - 2 * cm
            c.setFont("Helvetica", 10)
    if overview_path:
        c.showPage()
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2 * cm, h - 2 * cm, "Vista generale e numerazione pannelli")
        c.drawImage(str(overview_path), 1.5 * cm, 2.2 * cm, width=w - 3 * cm, height=h - 5 * cm, preserveAspectRatio=True, mask="auto")
    for p in panel_paths:
        c.showPage()
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2 * cm, h - 2 * cm, p.stem.replace("_", " ").title())
        c.drawImage(str(p), 1.5 * cm, 2.2 * cm, width=w - 3 * cm, height=h - 5 * cm, preserveAspectRatio=True, mask="auto")
    c.save()


def export_instructions_html(
    grid: Sequence[Sequence[PaletteColor]],
    html_path: str | Path,
    panel_size: int,
    part_name: str,
    plan: Sequence[dict[str, object]],
) -> None:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    panels = split_panels(grid, panel_size)
    legend = [
        {
            "abbr": color.name[:3].upper(),
            "name": color.name,
            "hex": color.hex,
            "count": count,
        }
        for color, count in build_inventory(grid)
    ]
    plan_by_color = {str(row["color_name"]): row for row in plan}
    panel_payload = []
    for px, py, subgrid in panels:
        panel_payload.append(
            {
                "name": f"Panel {py+1},{px+1}",
                "row": py + 1,
                "col": px + 1,
                "inventory": [{"name": name, "count": count} for name, count in build_panel_inventory(subgrid)],
                "cells": [
                    [
                        {
                            "abbr": c.name[:3].upper(),
                            "name": c.name,
                            "hex": c.hex,
                            "compatible": bool(plan_by_color.get(c.name, {}).get("available_for_piece", True)),
                        }
                        for c in row
                    ]
                    for row in subgrid
                ],
            }
        )
    payload = {
        "summary": {
            "width": cols,
            "height": rows,
            "panel_size": panel_size,
            "panels_x": math.ceil(cols / panel_size) if panel_size else 0,
            "panels_y": math.ceil(rows / panel_size) if panel_size else 0,
            "part_name": part_name,
            "estimated_cost_eur": round(sum(float(r.get("estimated_cost_eur", 0.0)) for r in plan), 2),
        },
        "legend": legend,
        "panels": panel_payload,
    }
    html = """<!DOCTYPE html>
<html lang=\"it\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>LEGO Mosaic Pro - Istruzioni HTML</title>
<style>
body { font-family: Arial, sans-serif; margin: 0; background:#f5f5f7; color:#111; }
header { padding: 20px 24px; background:#fff; box-shadow: 0 1px 4px rgba(0,0,0,.08); position: sticky; top:0; z-index:10; }
main { padding: 20px 24px 48px; max-width: 1440px; margin: 0 auto; }
.card { background:#fff; border-radius:14px; padding:16px; box-shadow:0 1px 4px rgba(0,0,0,.08); margin-bottom:18px; }
.summary { display:grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
.kpi { background:#fafafa; border:1px solid #e5e5e5; border-radius:12px; padding:12px; }
.controls { display:flex; gap:12px; flex-wrap:wrap; align-items:center; margin-top:12px; }
button, select, input { font: inherit; padding:8px 10px; border-radius:10px; border:1px solid #ccc; background:#fff; }
.layout { display:grid; grid-template-columns: minmax(280px, 1fr) 2fr; gap:18px; }
.gridwrap { overflow:auto; max-width:100%; border:1px solid #e5e5e5; border-radius:12px; }
table.grid { border-collapse: collapse; background:#fff; }
table.grid td { width:32px; height:32px; text-align:center; font-size:10px; font-weight:bold; border:1px solid rgba(0,0,0,.09); cursor:pointer; }
table.grid td.incompatible { outline: 3px solid #d22 inset; }
table.grid td.muted { opacity:.18; }
.legend { display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
.legend-item { display:flex; gap:10px; align-items:center; border:1px solid #ececec; border-radius:10px; padding:10px; cursor:pointer; }
.swatch { width:28px; height:28px; border-radius:8px; border:1px solid rgba(0,0,0,.12); flex:0 0 28px; }
.small { color:#555; font-size: 12px; }
#detail { min-height: 70px; }
#panelInventory table { width:100%; border-collapse: collapse; }
#panelInventory td, #panelInventory th { border-bottom:1px solid #eee; padding:6px 4px; text-align:left; }
</style>
</head>
<body>
<header>
  <h1 style=\"margin:0 0 6px\">LEGO Mosaic Pro - Istruzioni HTML</h1>
  <div class=\"small\">Visualizzatore interattivo pannello per pannello</div>
</header>
<main>
  <section class=\"card summary\" id=\"summary\"></section>
  <section class=\"card\">
    <div class=\"controls\">
      <label>Pannello <select id=\"panelSelect\"></select></label>
      <label>Zoom <input id=\"zoom\" type=\"range\" min=\"20\" max=\"60\" value=\"32\"></label>
      <button id=\"toggleNames\">Mostra/nascondi sigle</button>
      <button id=\"clearFilter\">Azzera filtro colore</button>
    </div>
    <div id=\"detail\" class=\"small\" style=\"margin:12px 0\">Clicca un pixel o un colore in legenda per filtrare.</div>
    <div class=\"layout\">
      <div class=\"card\" id=\"panelInventory\"><h3 style=\"margin-top:0\">Distinta del pannello</h3></div>
      <div class=\"gridwrap\"><table class=\"grid\" id=\"grid\"></table></div>
    </div>
  </section>
  <section class=\"card\">
    <h2 style=\"margin-top:0\">Legenda colori</h2>
    <div class=\"legend\" id=\"legend\"></div>
  </section>
</main>
<script id=\"payload\" type=\"application/json\">__PAYLOAD__</script>
<script>
const data = JSON.parse(document.getElementById('payload').textContent);
const summary = document.getElementById('summary');
const panelSelect = document.getElementById('panelSelect');
const grid = document.getElementById('grid');
const legend = document.getElementById('legend');
const detail = document.getElementById('detail');
const zoom = document.getElementById('zoom');
const panelInventory = document.getElementById('panelInventory');
let showNames = true;
let activeColor = null;
function kpi(label, value) {
  const d = document.createElement('div'); d.className='kpi';
  d.innerHTML = `<div class=\"small\">${label}</div><div><strong>${value}</strong></div>`;
  return d;
}
summary.append(
  kpi('Dimensioni', `${data.summary.width} x ${data.summary.height} stud`),
  kpi('Pannelli', `${data.summary.panels_x} x ${data.summary.panels_y} da ${data.summary.panel_size}x${data.summary.panel_size}`),
  kpi('Pezzo', data.summary.part_name),
  kpi('Stima costo', `EUR ${data.summary.estimated_cost_eur.toFixed(2)}`)
);
data.panels.forEach((p, i) => {
  const opt = document.createElement('option');
  opt.value = i; opt.textContent = p.name; panelSelect.appendChild(opt);
});
data.legend.forEach(item => {
  const el = document.createElement('div');
  el.className='legend-item';
  el.innerHTML = `<div class=\"swatch\" style=\"background:${item.hex}\"></div><div><div><strong>${item.abbr}</strong> - ${item.name}</div><div class=\"small\">${item.hex} · ${item.count} pezzi</div></div>`;
  el.onclick = () => { activeColor = item.name; renderPanel(Number(panelSelect.value || 0)); };
  legend.appendChild(el);
});
function textColor(hex) {
  const r=parseInt(hex.slice(1,3),16), g=parseInt(hex.slice(3,5),16), b=parseInt(hex.slice(5,7),16);
  return (r*299+g*587+b*114)/1000 > 150 ? '#111' : '#fff';
}
function renderPanelInventory(panel) {
  const rows = panel.inventory.map(row => `<tr><td>${row.name}</td><td>${row.count}</td></tr>`).join('');
  panelInventory.innerHTML = `<h3 style=\"margin-top:0\">Distinta del pannello</h3><div class=\"small\">${panel.name}</div><table><thead><tr><th>Colore</th><th>Q.tà</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderPanel(idx) {
  const panel = data.panels[idx];
  grid.innerHTML='';
  renderPanelInventory(panel);
  panel.cells.forEach((row, y) => {
    const tr = document.createElement('tr');
    row.forEach((cell, x) => {
      const td = document.createElement('td');
      td.style.background = cell.hex;
      td.style.color = textColor(cell.hex);
      td.style.width = zoom.value + 'px';
      td.style.height = zoom.value + 'px';
      td.textContent = showNames ? cell.abbr : '';
      if (!cell.compatible) td.classList.add('incompatible');
      if (activeColor && cell.name !== activeColor) td.classList.add('muted');
      td.title = `${cell.name} (${x+1},${y+1})`;
      td.onclick = () => {
        detail.innerHTML = `<strong>${panel.name}</strong> · Riga ${y+1} Colonna ${x+1} · <strong>${cell.name}</strong> · ${cell.hex}${cell.compatible ? '' : ' · non compatibile col pezzo selezionato'}`;
      };
      tr.appendChild(td);
    });
    grid.appendChild(tr);
  });
}
panelSelect.onchange = () => renderPanel(Number(panelSelect.value));
zoom.oninput = () => renderPanel(Number(panelSelect.value || 0));
document.getElementById('toggleNames').onclick = () => { showNames = !showNames; renderPanel(Number(panelSelect.value || 0)); };
document.getElementById('clearFilter').onclick = () => { activeColor = null; renderPanel(Number(panelSelect.value || 0)); };
renderPanel(0);
</script>
</body>
</html>
"""
    html = html.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
    Path(html_path).write_text(html, encoding="utf-8")


# ---------- orchestration ----------

def maybe_limit_palette(image: Image.Image, palette: Sequence[PaletteColor], max_colors: int | None, dither: bool) -> list[PaletteColor]:
    if not max_colors or max_colors >= len(palette):
        return list(palette)
    base = floyd_steinberg_dither(image, palette) if dither else image
    _, grid = quantize_to_palette(base, palette)
    reduced, _ = reduce_palette_to_top_colors(grid, max_colors)
    return reduced


def generate_mosaic(input_image: str | Path, palette_path: str | Path, output_dir: str | Path, config: MosaicConfig) -> dict[str, str]:
    validate_config(config)
    input_image = Path(input_image)
    palette_path = Path(palette_path)
    output_dir = Path(output_dir)
    if not input_image.exists():
        raise FileNotFoundError(f"Immagine di input non trovata: {input_image}")
    if not palette_path.exists():
        raise FileNotFoundError(f"Palette XML non trovata: {palette_path}")
    if config.catalog_path and not Path(config.catalog_path).exists():
        raise FileNotFoundError(f"Catalogo pezzi non trovato: {config.catalog_path}")
    if config.owned_inventory_path and not Path(config.owned_inventory_path).exists():
        raise FileNotFoundError(f"Inventario posseduto non trovato: {config.owned_inventory_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    instructions_dir = output_dir / "instructions"
    instructions_dir.mkdir(exist_ok=True)

    palette = load_palette(
        palette_path,
        include_materials=config.include_materials,
        exclude_materials=config.exclude_materials,
        current_only=config.current_only,
    )
    catalog = None
    owned: dict[str, int] = {}
    if config.catalog_path:
        catalog = load_catalog(config.catalog_path, config.piece_type)
        if config.piece_aware_palette:
            allowed_names = {name for name, entry in catalog.items() if entry.available}
            filtered_palette = [p for p in palette if p.name in allowed_names]
            if filtered_palette:
                palette = filtered_palette
        if config.owned_inventory_path:
            owned = load_owned_inventory(config.owned_inventory_path, config.piece_type)

    image = Image.open(input_image).convert("RGB")
    width = config.width
    height = config.height or infer_height_preserving_aspect(image, width)
    if config.enforce_panel_multiple:
        width = enforce_multiple(width, config.panel_size)
        height = enforce_multiple(height, config.panel_size)
    image = fit_or_fill(image, width, height, config.crop_mode)
    image = preprocess_image(image, config.contrast, config.saturation, config.sharpen)
    palette = maybe_limit_palette(image, palette, config.max_colors, config.dither)
    working = floyd_steinberg_dither(image, palette) if config.dither else image
    pixel_art, grid = quantize_to_palette(working, palette)

    pixel_art_path = output_dir / "mosaic.png"
    pixel_preview_path = output_dir / "preview_pixel.png"
    stud_preview_path = output_dir / "preview_stud.png"
    grid_csv_path = output_dir / "grid.csv"
    inventory_csv_path = output_dir / "inventory.csv"
    purchase_plan_path = output_dir / "purchase_plan.csv"
    compatibility_path = output_dir / "piece_compatibility.csv"
    cost_summary_path = output_dir / "cost_summary.txt"
    panel_inventory_path = output_dir / "panel_inventory.csv"
    legend_csv_path = instructions_dir / "legend.csv"
    summary_txt_path = output_dir / "summary.txt"
    pdf_path = output_dir / "instructions.pdf"
    html_path = output_dir / "instructions.html"
    overview_path = output_dir / "overview.png"
    wanted_list_path = output_dir / "bricklink_wanted_list.xml"
    report_json_path = output_dir / "report.json"

    pixel_art.save(pixel_art_path)
    save_pixel_preview(pixel_art, pixel_preview_path, config.pixel_preview_scale)
    stud_preview_generated = False
    overview_generated = False
    if config.generate_stud_preview:
        render_stud_preview(grid, cell=config.stud_preview_scale).save(stud_preview_path)
        stud_preview_generated = True
    if config.generate_overview:
        render_overview(grid, config.panel_size).save(overview_path)
        overview_generated = True

    export_grid_csv(grid, grid_csv_path)
    export_inventory_csv(grid, inventory_csv_path)
    export_legend_csv(grid, legend_csv_path)
    export_panel_inventory_csv(grid, config.panel_size, panel_inventory_path)
    export_summary_txt(grid, summary_txt_path, config.panel_size, config.piece_type, config.max_colors)
    panel_paths = export_panels(grid, instructions_dir, config.panel_size)

    catalog_info: dict[str, str] = {}
    plan: list[dict[str, object]] = []
    if catalog is not None:
        plan = compute_purchase_plan(grid, catalog, owned)
        export_purchase_plan_csv(plan, purchase_plan_path)
        export_compatibility_csv(plan, compatibility_path)
        export_cost_summary_txt(plan, cost_summary_path, config.part_name)
        if config.generate_wanted_list:
            export_wanted_list_xml(plan, wanted_list_path)
        catalog_info = {
            "purchase_plan_csv": str(purchase_plan_path),
            "piece_compatibility_csv": str(compatibility_path),
            "cost_summary_txt": str(cost_summary_path),
            "estimated_cost_eur": f"{sum(float(r['estimated_cost_eur']) for r in plan):.2f}",
            "incompatible_colors": str(sum(1 for r in plan if not r['available_for_piece'])),
            "bricklink_wanted_list": str(wanted_list_path),
        }

    pdf_generated = False
    if config.generate_pdf:
        export_instructions_pdf(grid, pdf_path, panel_paths, config.panel_size, plan, config.part_name, overview_path if overview_generated else None)
        pdf_generated = True
    export_instructions_html(grid, html_path, config.panel_size, config.part_name, plan)

    report = {
        "input_image": str(input_image),
        "output_dir": str(output_dir),
        "piece_type": config.piece_type,
        "part_name": config.part_name,
        "dimensions": {"width": pixel_art.width, "height": pixel_art.height, "panel_size": config.panel_size},
        "palette": {"path": str(palette_path), **palette_stats(palette)},
        "used_colors": [{"name": color.name, "count": count, "hex": color.hex} for color, count in build_inventory(grid)],
        "estimated_cost_eur": round(sum(float(r.get("estimated_cost_eur", 0.0)) for r in plan), 2),
        "files": {
            "mosaic": str(pixel_art_path),
            "preview_pixel": str(pixel_preview_path),
            "preview_stud": str(stud_preview_path) if stud_preview_generated else "",
            "overview": str(overview_path) if overview_generated else "",
            "instructions_html": str(html_path),
            "instructions_pdf": str(pdf_path) if pdf_generated else "",
            "inventory_csv": str(inventory_csv_path),
            "grid_csv": str(grid_csv_path),
            "panel_inventory_csv": str(panel_inventory_path),
            "purchase_plan_csv": str(purchase_plan_path),
            "piece_compatibility_csv": str(compatibility_path),
            "bricklink_wanted_list": str(wanted_list_path),
        },
    }
    if config.generate_json_report:
        export_json_report(report, report_json_path)

    result = {
        "mosaic": str(pixel_art_path),
        "preview_pixel": str(pixel_preview_path),
        "preview_stud": str(stud_preview_path) if stud_preview_generated else "",
        "overview": str(overview_path) if overview_generated else "",
        "grid_csv": str(grid_csv_path),
        "inventory_csv": str(inventory_csv_path),
        "panel_inventory_csv": str(panel_inventory_path),
        "summary_txt": str(summary_txt_path),
        "instructions_pdf": str(pdf_path) if pdf_generated else "",
        "instructions_html": str(html_path),
        "instructions_dir": str(instructions_dir),
        "report_json": str(report_json_path),
        "palette_used": str(palette_path.resolve()),
        "palette_size": str(len(palette)),
        "width": str(pixel_art.width),
        "height": str(pixel_art.height),
        "piece_type": config.piece_type,
        "max_colors": str(config.max_colors or ""),
    }
    result.update(catalog_info)
    return result
