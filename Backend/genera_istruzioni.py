# =========================
# BRIXEL MY PIC - PRO COVER + INDICE
# HTML/CSS + WeasyPrint only
# =========================

from pathlib import Path
from weasyprint import HTML
import os
import csv
import re
import sys
import time
import math
import tempfile
import shutil

# =========================
# CONFIG
# =========================
OUTPUT_PDF = "demo_output.pdf"
JOB_PATH = Path("/opt/fastapi-app/storage/jobs/LEO-YE87OX")

ENABLE_LOG = "-log" in sys.argv

# 2 = totale pagine sempre pari
# 4 = consigliato se vuoi una segnatura più comoda per booklet
FORCE_TOTAL_PAGES_MULTIPLE = 2

PANEL_SIZE = 16
NUM_BOM_COLUMNS = 4
ROWS_PER_BOM_COLUMN = 6
MAX_ITEMS_PER_PANEL_PAGE = NUM_BOM_COLUMNS * ROWS_PER_BOM_COLUMN  # 24

BASE_FONT_SCALE = 0.75

BRAND_TITLE = "Brixel My Pic!"
BRAND_SUBTITLE = "Libretto istruzioni mosaico · Stile LEGO · Stampa A4 booklet-ready"
BRAND_NAME = "LEOBRICK"

FOOTER_LINE_1 = "© 2026 LeoBrick – Tutti i diritti riservati. | www.leobrick.com"
FOOTER_LINE_2 = "Powered by ABRDome divisione informatica"
FOOTER_LINE_3_TEMPLATE = "Pagina {page_num} / {total_pages}"

PdfWriter = None
try:
    from pypdf import PdfWriter
except Exception:
    PdfWriter = None


# =========================
# LOG / PROGRESS
# =========================
def log(msg: str):
    if ENABLE_LOG:
        print(msg)


def print_progress(current: int, total: int, start_time: float, prefix: str = ""):
    if not ENABLE_LOG:
        return
    total = max(total, 1)
    progress = current / total
    bar_length = 30
    filled = int(bar_length * progress)
    bar = "█" * filled + "-" * (bar_length - filled)
    elapsed = time.time() - start_time
    avg = elapsed / current if current else 0
    remaining = int(avg * (total - current))
    sys.stdout.write(f"\r{prefix}[{bar}] {current}/{total} | ETA {remaining}s")
    sys.stdout.flush()


def finish_progress():
    if ENABLE_LOG:
        print("")


# =========================
# UTILITIES
# =========================
def compute_bom_layout(items):
    count = len(items)

    if count <= 8:
        return {"columns": 2, "rows": 4, "font": 1.0, "dot": 6}

    if count <= 18:
        return {"columns": 3, "rows": 6, "font": 0.95, "dot": 5}

    return {"columns": 3, "rows": 8, "font": 0.85, "dot": 5}

def escape_html(value):
    if value is None:
        return ""
    value = str(value)
    return (
        value.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
    )


def chunk_list(lst, size):
    if size <= 0:
        return [lst]
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def split_into_columns(items, num_columns=3, rows_per_column=12):
    columns = []
    start = 0
    for _ in range(num_columns):
        end = start + rows_per_column
        columns.append(items[start:end])
        start = end
    return columns


def pad_pages_to_multiple(page_specs, multiple):
    remainder = len(page_specs) % multiple
    if remainder == 0:
        return page_specs
    missing = multiple - remainder
    for _ in range(missing):
        page_specs.append({
            "kind": "blank",
            "content": render_blank_page_content(),
        })
    return page_specs

def inject_page_numbers(page_specs):
    total = len(page_specs)
    for i, p in enumerate(page_specs, start=1):
        p["page_num"] = i
        p["total_pages"] = total
    return page_specs

def hex_to_rgb_tuple(hex_color: str):
    if not hex_color:
        return (204, 204, 204)
    s = hex_color.strip().lstrip("#")
    if len(s) != 6:
        return (204, 204, 204)
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (204, 204, 204)


def ideal_text_color(hex_color: str):
    r, g, b = hex_to_rgb_tuple(hex_color)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    return "#111111" if luminance > 165 else "#FFFFFF"


def panel_sort_key(key):
    return (key[0], key[1])


def get_total_panel_layout(grid):
    if not grid:
        return (0, 0)
    h = len(grid)
    w = len(grid[0]) if grid[0] else 0
    return (math.ceil(h / PANEL_SIZE), math.ceil(w / PANEL_SIZE))


# =========================
# CSV LOADERS
# =========================
def load_inventory(job_path: Path):
    """
    inventory.csv
    name;count;rgb;material;lego_id;bricklink_id;ldraw_id
    """
    inventory = {}
    path = job_path / "inventory.csv"
    if not path.exists():
        return inventory

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue

            inventory[name] = {
                "name": name,
                "count": int((row.get("count") or "0").strip() or 0),
                "rgb": (row.get("rgb") or "#CCCCCC").strip(),
                "material": (row.get("material") or "").strip(),
                "lego_id": (row.get("lego_id") or "").strip(),
                "bricklink_id": (row.get("bricklink_id") or "").strip(),
                "ldraw_id": (row.get("ldraw_id") or "").strip(),
            }
    return inventory


def load_legend(job_path: Path):
    """
    instructions/legend.csv
    abbr;name;rgb;lego_id;bricklink_id
    """
    legend = {}
    path = job_path / "instructions" / "legend.csv"
    if not path.exists():
        return legend

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue

            legend[name] = {
                "abbr": (row.get("abbr") or "").strip(),
                "name": name,
                "rgb": (row.get("rgb") or "#CCCCCC").strip(),
                "lego_id": (row.get("lego_id") or "").strip(),
                "bricklink_id": (row.get("bricklink_id") or "").strip(),
            }
    return legend


def load_panel_inventory(job_path: Path):
    """
    panel_inventory.csv
    panel_row;panel_col;color_name;count
    """
    panels = {}
    path = job_path / "panel_inventory.csv"
    if not path.exists():
        return panels

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            panel_row = int((row.get("panel_row") or "0").strip() or 0)
            panel_col = int((row.get("panel_col") or "0").strip() or 0)
            color_name = (row.get("color_name") or "").strip()
            count = int((row.get("count") or "0").strip() or 0)

            if not color_name:
                continue

            key = (panel_row, panel_col)
            panels.setdefault(key, []).append({
                "color_name": color_name,
                "count": count,
            })
    return panels


def load_panels(job_path: Path):
    """
    instructions/panel_01_01.png
    """
    folder = job_path / "instructions"
    panel_map = {}
    if not folder.exists():
        return panel_map

    pattern = re.compile(r"panel_(\d{2})_(\d{2})\.png$", re.IGNORECASE)
    for filename in os.listdir(folder):
        match = pattern.match(filename)
        if not match:
            continue

        panel_row = int(match.group(1))
        panel_col = int(match.group(2))
        key = (panel_row, panel_col)
        panel_map[key] = (folder / filename).resolve().as_uri()

    return dict(sorted(panel_map.items(), key=lambda x: panel_sort_key(x[0])))


def load_grid(job_path: Path):
    """
    grid.csv
    row;x1;x2;...;x144
    y1;White;White;...
    """
    path = job_path / "grid.csv"
    grid = []
    if not path.exists():
        return grid

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        try:
            next(reader)
        except StopIteration:
            return grid

        for row in reader:
            if not row:
                continue
            grid.append(row[1:])
    return grid


# =========================
# DATA
# =========================
def generate_data():
    original_path = (JOB_PATH / "input_image.png").resolve().as_uri()
    overview_path = (JOB_PATH / "overview.png").resolve().as_uri()

    data = {
        "original": original_path,
        "overview": overview_path,
        "inventory": load_inventory(JOB_PATH),
        "legend": load_legend(JOB_PATH),
        "panel_inventory": load_panel_inventory(JOB_PATH),
        "panels": load_panels(JOB_PATH),
        "grid": load_grid(JOB_PATH),
    }
    return data


# =========================
# COLOR META
# =========================
def get_color_meta(color_name: str, legend: dict, inventory: dict):
    leg = legend.get(color_name, {})
    inv = inventory.get(color_name, {})

    abbr = (leg.get("abbr") or "")[:4].upper()
    if not abbr:
        abbr = color_name[:3].upper()

    rgb = leg.get("rgb") or inv.get("rgb") or "#CCCCCC"

    return {
        "name": color_name,
        "abbr": abbr,
        "rgb": rgb,
        "text_color": ideal_text_color(rgb),
        "lego_id": leg.get("lego_id") or inv.get("lego_id") or "",
        "bricklink_id": leg.get("bricklink_id") or inv.get("bricklink_id") or "",
        "count": inv.get("count", 0),
    }


# =========================
# GRID ENGINE
# =========================
def extract_panel_grid(grid, panel_row, panel_col, panel_size=PANEL_SIZE):
    if not grid:
        return []

    start_y = (panel_row - 1) * panel_size
    start_x = (panel_col - 1) * panel_size

    subgrid = []
    for y in range(start_y, min(start_y + panel_size, len(grid))):
        row = grid[y]
        subgrid.append(row[start_x:start_x + panel_size])

    return subgrid


def render_grid_html(subgrid, legend, inventory):
    if not subgrid:
        return '<div class="muted">Griglia non disponibile</div>'

    letters = [chr(ord("A") + i) for i in range(len(subgrid[0]))]

    html = '<table class="grid-table">'
    html += '<tr>'
    html += '<th class="grid-corner"></th>'
    for letter in letters:
        html += f'<th class="grid-col-head">{letter}</th>'
    html += '</tr>'

    for idx, row in enumerate(subgrid, start=1):
        html += '<tr>'
        html += f'<th class="grid-row-head">{idx}</th>'
        for cell in row:
            meta = get_color_meta(cell, legend, inventory)
            html += (
                f'<td class="grid-cell" '
                f'style="background:{meta["rgb"]}; color:{meta["text_color"]};">'
                f'{escape_html(meta["abbr"])}'
                f'</td>'
            )
        html += '</tr>'

    html += '</table>'
    return html


def render_grid_legend_strip(subgrid, legend, inventory):
    if not subgrid:
        return ""

    used = {}
    for row in subgrid:
        for color_name in row:
            if color_name not in used:
                used[color_name] = get_color_meta(color_name, legend, inventory)

    items = sorted(used.values(), key=lambda x: x["name"])
    items = items[:8]

    cells = ""
    for item in items:
        cells += f"""
        <td class="legend-chip">
            <span class="inv-swatch" style="background:{item['rgb']};"></span>
            {escape_html(item['abbr'])} · {escape_html(item['name'])}
        </td>
        """

    return f"""
    <table class="legend-strip" cellspacing="0" cellpadding="0">
        <tr>{cells}</tr>
    </table>
    """


# =========================
# BOM
# =========================
def render_bom_item(item, legend, inventory, layout):
    meta = get_color_meta(item["color_name"], legend, inventory)

    return f"""
    <table class="bom-item" style="font-size:{layout['font']}em;">
        <tr>
            <td style="width:6mm;text-align:center;">
                <div style="
                    width:{layout['dot']}mm;
                    height:{layout['dot']}mm;
                    border-radius:50%;
                    background:{meta['rgb']};
                    border:0.2mm solid #333;
                "></div>
            </td>
            <td style="width:10mm;font-weight:bold;">
                {meta['abbr']}
            </td>
            <td style="overflow:hidden;">
                <div style="font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                    {escape_html(meta['name'])}
                </div>
                <div style="font-size:0.7em;color:#666;">
                    LEGO {meta['lego_id']}
                </div>
            </td>
            <td style="width:8mm;text-align:right;font-weight:bold;">
                {item['count']}
            </td>
        </tr>
    </table>
    """


def render_bom_columns(items, legend, inventory):

    layout = compute_bom_layout(items)

    cols = layout["columns"]
    rows = layout["rows"]
    max_items = cols * rows

    items = sorted(items, key=lambda x: x["count"], reverse=True)[:max_items]

    columns_data = split_into_columns(items, cols, rows)

    html = ""

    for col_items in columns_data:
        inner = ""
        for item in col_items:
            inner += render_bom_item(item, legend, inventory, layout)

        html += f"""
        <td style="width:{100/cols}%;vertical-align:top;">
            {inner}
        </td>
        """

    return f"""
    <table style="width:100%;border-spacing:1mm 0;" data-cols="{cols}">
        <tr>{html}</tr>
    </table>
    """


# =========================
# PAGE CONTENT RENDERERS
# =========================
def render_cover_page_content(data):
    total_panels = len(data["panels"])
    total_colors = len(data["inventory"])
    total_rows, total_cols = get_total_panel_layout(data["grid"])
    grid_h = len(data["grid"])
    grid_w = len(data["grid"][0]) if data["grid"] else 0

    return f"""
    <div class="cover-shell">
        <div class="cover-topline">{escape_html(BRAND_NAME)}</div>

        <table class="cover-header-table" cellspacing="0" cellpadding="0">
            <tr>
                <td class="cover-header-left">
                    <div class="cover-title">{escape_html(BRAND_TITLE)}</div>
                    <div class="cover-subtitle">{escape_html(BRAND_SUBTITLE)}</div>
                </td>
                <td class="cover-header-right">
                    <div class="cover-badge">PRO GUIDE</div>
                </td>
            </tr>
        </table>

        <div class="cover-stats-wrapper">
            <table class="cover-stats" cellspacing="0" cellpadding="0">
                <tr>
                    <td class="cover-stat-card">
                        <div class="cover-stat-title">Dimensione mosaico</div>
                        <div class="cover-stat-value">{grid_w} × {grid_h} pixel/bricks</div>
                    </td>
                    <td class="cover-stat-card">
                        <div class="cover-stat-title">Pannelli</div>
                        <div class="cover-stat-value">{total_panels} pannelli da {PANEL_SIZE} × {PANEL_SIZE}</div>
                    </td>
                    <td class="cover-stat-card">
                        <div class="cover-stat-title">Layout</div>
                        <div class="cover-stat-value">{total_rows} righe × {total_cols} colonne</div>
                    </td>
                    <td class="cover-stat-card">
                        <div class="cover-stat-title">Colori</div>
                        <div class="cover-stat-value">{total_colors} colori distinti</div>
                    </td>
                </tr>
            </table>
        </div>

        <div class="cover-image-box">
            <img src="{data['original']}" alt="Immagine originale">
        </div>

        <table class="cover-bottom-table" cellspacing="0" cellpadding="0">
            <tr>
                <td class="cover-tip-card">
                    <div class="cover-tip-title">Suggerimento</div>
                    <div class="cover-tip-text">
                        Prepara prima i colori globali e poi lavora pannello per pannello seguendo l’indice.
                    </div>
                </td>
                <td class="cover-tip-card">
                    <div class="cover-tip-title">Formato</div>
                    <div class="cover-tip-text">
                        Questo PDF è impaginato in formato A4 ed è pronto per stampa e piega a libretto.
                    </div>
                </td>
            </tr>
        </table>
    </div>
    """


def render_index_pages_content(data):
    """
    Indice pannelli con numero pagina reale.
    Per costruirlo correttamente, il mapping pagina viene generato prima in build_page_specs().
    Qui usiamo un placeholder e poi sostituiamo nella seconda passata.
    """
    return []


def render_overview_page_content(data):
    total_rows, total_cols = get_total_panel_layout(data["grid"])

    return f"""
    <div class="section-kicker">Panoramica</div>
    <div class="section-title">Vista generale del mosaico</div>
    <div class="section-subtitle">
        Suddivisione pannelli: {total_rows} righe × {total_cols} colonne.
        Usa questa pagina come riferimento rapido prima di iniziare l’assemblaggio.
    </div>

    <div class="hero-image-box">
        <img src="{data['overview']}" alt="Overview pixel art">
    </div>

    <div class="overview-note-box">
        <div class="overview-note-title">Flusso consigliato</div>
        <div class="overview-note-text">
            1. Consulta l’indice pannelli.<br>
            2. Recupera i colori necessari per il pannello corrente.<br>
            3. Segui lo schema di montaggio 16×16.<br>
            4. Procedi al pannello successivo.
        </div>
    </div>
    """


def render_inventory_pages_content(data):
    items = []
    for color_name, inv in data["inventory"].items():
        meta = get_color_meta(color_name, data["legend"], data["inventory"])
        items.append({
            "name": meta["name"],
            "abbr": meta["abbr"],
            "rgb": meta["rgb"],
            "lego_id": meta["lego_id"],
            "bricklink_id": meta["bricklink_id"],
            "count": inv.get("count", 0),
        })

    items.sort(key=lambda x: (-x["count"], x["name"]))

    rows_per_page = 24
    chunks = chunk_list(items, rows_per_page)
    if not chunks:
        chunks = [[]]

    pages = []
    total = len(chunks)

    for idx, chunk in enumerate(chunks, start=1):
        rows_html = ""
        for row in chunk:
            rows_html += f"""
            <tr>
                <td><span class="inv-swatch" style="background:{row['rgb']};"></span></td>
                <td>{escape_html(row['abbr'])}</td>
                <td>{escape_html(row['name'])}</td>
                <td class="muted">{escape_html(row['lego_id'])}</td>
                <td class="muted">{escape_html(row['bricklink_id'])}</td>
                <td class="inv-qty">{row['count']}</td>
            </tr>
            """

        pages.append(f"""
        <div class="section-kicker">Distinta generale</div>
        <div class="section-title">Colori totali del progetto</div>
        <div class="section-subtitle">Pagina distinta {idx}/{total}</div>

        <div class="inventory-box" style="margin-top:6mm;">
            <table class="inventory-table">
                <thead>
                    <tr>
                        <th style="width:8mm;">&nbsp;</th>
                        <th style="width:12mm;">Cod.</th>
                        <th>Colore</th>
                        <th style="width:26mm;">LEGO ID</th>
                        <th style="width:26mm;">BL ID</th>
                        <th style="width:16mm; text-align:right;">Qtà</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
        """)

    return pages


def render_panel_page_content(data, panel_row, panel_col, items, chunk_index, chunk_total):
    subgrid = extract_panel_grid(data["grid"], panel_row, panel_col, PANEL_SIZE)
    grid_html = render_grid_html(subgrid, data["legend"], data["inventory"])
    grid_legend = render_grid_legend_strip(subgrid, data["legend"], data["inventory"])

    panel_label = f"Pannello {panel_row},{panel_col}"
    page_label = f"Parte {chunk_index}/{chunk_total}"

    items_sorted = sorted(items, key=lambda x: x["count"], reverse=True)
    bom_html = render_bom_columns(items_sorted, data["legend"], data["inventory"])

    return f"""
    <div class="panel-header-box">
        <table class="header-table" cellspacing="0" cellpadding="0">
            <tr>
                <td class="header-left">
                    <div class="kicker">{escape_html(BRAND_TITLE)}</div>
                    <div class="title">{escape_html(panel_label)}</div>
                    <div class="subtitle">{escape_html(page_label)}</div>
                </td>
                <td class="header-right">
                    <div class="meta">Griglia {PANEL_SIZE}×{PANEL_SIZE}</div>
                </td>
            </tr>
        </table>
    </div>

    <div class="panel-bom-box">
        <div class="panel-section-title">Colori necessari</div>
        {bom_html}
    </div>

    <div class="grid-box" style="margin-top:5mm;">
        <div class="grid-title">Schema di montaggio</div>
        {grid_html}
    </div>
    """


def render_legal_page_content():
    return f"""
    <div class="section-kicker">Informazioni</div>
    <div class="section-title">Note legali e credits</div>
    <div class="section-subtitle">
        Retrospizio del libretto.
    </div>

    <div class="legal-box">
        <div class="legal-title">Disclaimer</div>
        <div class="legal-text">
            LEGO® è un marchio registrato di The LEGO Group, che non sponsorizza,
            autorizza o approva questo prodotto. Questo libretto è un elaborato
            indipendente generato per la costruzione di mosaici personalizzati.
        </div>
    </div>

    <div class="legal-box">
        <div class="legal-title">Credits</div>
        <div class="legal-text">
            {escape_html(BRAND_TITLE)} è un servizio di {escape_html(BRAND_NAME)}.<br>
            PDF generato tramite pipeline Python + HTML/CSS + WeasyPrint.<br>
            Powered by ABR Dome Software House.
        </div>
    </div>

    <div class="legal-box">
        <div class="legal-title">Stampa</div>
        <div class="legal-text">
            Per una stampa a libretto più comoda puoi impostare il totale pagine
            a multiplo di 4 cambiando la costante FORCE_TOTAL_PAGES_MULTIPLE.
        </div>
    </div>
    """


def render_blank_page_content():
    return """
    <div class="blank-page-note">
        Pagina lasciata intenzionalmente vuota
    </div>
    """


# =========================
# INDEX HELPERS
# =========================
def build_panel_entries(data):
    """
    Restituisce:
    - una lista ordinata di entry per indice
    - e le specifiche pannello per le pagine reali
    """
    entries = []
    panel_page_specs = []

    for (panel_row, panel_col) in sorted(data["panels"].keys(), key=panel_sort_key):
        items = data["panel_inventory"].get((panel_row, panel_col), [])
        items_sorted = sorted(items, key=lambda x: x["count"], reverse=True)
        chunks = chunk_list(items_sorted, MAX_ITEMS_PER_PANEL_PAGE)
        if not chunks:
            chunks = [[]]

        chunk_total = len(chunks)

        entries.append({
            "panel_row": panel_row,
            "panel_col": panel_col,
            "parts": chunk_total,
        })

        for idx, chunk in enumerate(chunks, start=1):
            panel_page_specs.append({
                "kind": "panel",
                "panel_row": panel_row,
                "panel_col": panel_col,
                "chunk_index": idx,
                "chunk_total": chunk_total,
                "content": render_panel_page_content(
                    data=data,
                    panel_row=panel_row,
                    panel_col=panel_col,
                    items=chunk,
                    chunk_index=idx,
                    chunk_total=chunk_total,
                )
            })

    return entries, panel_page_specs


def render_index_page_chunk(chunk, page_idx, total_idx_pages):
    rows_html = ""
    for entry in chunk:
        part_text = f"{entry['parts']} parti" if entry["parts"] > 1 else "1 parte"
        page_ref = escape_html(entry.get("page_ref", "—"))
        rows_html += f"""
        <tr>
            <td class="index-col-panel">Pannello {entry['panel_row']},{entry['panel_col']}</td>
            <td class="index-col-parts">{part_text}</td>
            <td class="index-col-page">{page_ref}</td>
        </tr>
        """

    return f"""
    <div class="section-kicker">Indice</div>
    <div class="section-title">Mappa pannelli</div>
    <div class="section-subtitle">Pagina indice {page_idx}/{total_idx_pages}</div>

    <div class="index-box" style="margin-top:6mm;">
        <table class="index-table">
            <thead>
                <tr>
                    <th>Pannello</th>
                    <th style="width:28mm;">Split</th>
                    <th style="width:22mm; text-align:right;">Pagina</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    """


# =========================
# PAGE SPEC BUILDER
# =========================
def build_page_specs(data):
    """
    Costruisce le pagine in due passaggi:
    1) crea tutte le specifiche
    2) calcola le pagine reali per l’indice
    3) ricrea l’indice con i numeri corretti
    """
    panel_entries, panel_page_specs = build_panel_entries(data)

    # placeholder index
    index_rows_per_page = 28
    index_chunks = chunk_list(panel_entries, index_rows_per_page)
    if not index_chunks:
        index_chunks = [[]]

    index_placeholder_specs = []
    for idx, chunk in enumerate(index_chunks, start=1):
        index_placeholder_specs.append({
            "kind": "index",
            "content": render_index_page_chunk(chunk, idx, len(index_chunks))
        })

    inventory_pages = render_inventory_pages_content(data)
    inventory_specs = [{"kind": "inventory", "content": c} for c in inventory_pages]

    page_specs = []
    page_specs.append({"kind": "cover", "content": render_cover_page_content(data)})
    page_specs.extend(index_placeholder_specs)
    page_specs.append({"kind": "overview", "content": render_overview_page_content(data)})
    page_specs.extend(inventory_specs)
    page_specs.extend(panel_page_specs)
    page_specs.append({"kind": "legal", "content": render_legal_page_content()})

    # Calcolo pagine pannello reali
    panel_first_page = {}
    current_page_num = 1
    for spec in page_specs:
        if spec["kind"] == "panel":
            key = (spec["panel_row"], spec["panel_col"])
            if key not in panel_first_page:
                panel_first_page[key] = current_page_num
        current_page_num += 1

    # Aggiorna indice con pagina reale di inizio pannello
    updated_entries = []
    for entry in panel_entries:
        key = (entry["panel_row"], entry["panel_col"])
        start_page = panel_first_page.get(key)
        if start_page is None:
            page_ref = "—"
        else:
            if entry["parts"] > 1:
                end_page = start_page + entry["parts"] - 1
                page_ref = f"{start_page}-{end_page}"
            else:
                page_ref = f"{start_page}"

        new_entry = dict(entry)
        new_entry["page_ref"] = page_ref
        updated_entries.append(new_entry)

    # Ricrea indice definitivo
    final_index_specs = []
    final_index_chunks = chunk_list(updated_entries, index_rows_per_page)
    if not final_index_chunks:
        final_index_chunks = [[]]

    for idx, chunk in enumerate(final_index_chunks, start=1):
        final_index_specs.append({
            "kind": "index",
            "content": render_index_page_chunk(chunk, idx, len(final_index_chunks))
        })

    final_page_specs = []
    final_page_specs.append({"kind": "cover", "content": render_cover_page_content(data)})
    final_page_specs.extend(final_index_specs)
    final_page_specs.append({"kind": "overview", "content": render_overview_page_content(data)})
    final_page_specs.extend(inventory_specs)
    final_page_specs.extend(panel_page_specs)
    final_page_specs.append({"kind": "legal", "content": render_legal_page_content()})

    final_page_specs = pad_pages_to_multiple(final_page_specs, FORCE_TOTAL_PAGES_MULTIPLE)
    final_page_specs = inject_page_numbers(final_page_specs)

    return final_page_specs


# =========================
# DOCUMENT WRAPPER
# =========================
def render_footer_html(page_num: int, total_pages: int):
    return f"""
    <div class="footer">
        <div class="footer-line">{escape_html(FOOTER_LINE_1)}</div>
        <div class="footer-line">{escape_html(FOOTER_LINE_2)}</div>
        <div class="footer-line">{escape_html(FOOTER_LINE_3_TEMPLATE.format(page_num=page_num, total_pages=total_pages))}</div>
    </div>
    """


def wrap_page(content_html: str, page_num: int, total_pages: int):
    footer = render_footer_html(page_num, total_pages)
    return f"""
    <div class="page">
        <div class="page-shell">
            <div class="page-content">
                {content_html}
            </div>
            {footer}
        </div>
    </div>
    """


def render_document(page_specs):
    pages_html = []

    for idx, spec in enumerate(page_specs, start=1):
        page_num = spec.get("page_num", idx)
        total_pages = spec.get("total_pages", len(page_specs))

        pages_html.append(
            wrap_page(spec["content"], page_num, total_pages)
        )

    return f"""
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<style>

@page {{
    size: A4;
    margin: 10mm 14mm 18mm 14mm;
}}

* {{
    box-sizing: border-box;
}}

html, body {{
    margin: 0;
    padding: 0;
}}

body {{
    font-family: Arial, Helvetica, sans-serif;
    color: #111;
    font-size: {BASE_FONT_SCALE * 100:.0f}%;
}}

.page {{
    page-break-after: always;
}}

.page:last-child {{
    page-break-after: auto;
}}

.page-shell {{
    position: relative;
    height: 275mm;
}}

.page-content {{
    width: 100%;
    max-width: 180mm;
    margin: 0 auto;
    overflow: visible;
}}

.cover-stats-wrapper {{
    width: 142mm;
    margin: 5mm auto 8mm auto;
}}

.cover-stats {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 1.4mm 0;
    table-layout: fixed;
}}

.cover-stat-card {{
    width: 25%;
    background: #F6F6F6;
    border: 0.35mm solid #DEDEDE;
    border-radius: 2.2mm;
    padding: 1.6mm 1.8mm 1.7mm 1.8mm;
    vertical-align: top;
    box-shadow: inset 0 0.4mm 0 rgba(255,255,255,0.75);
}}

table {{
    max-width: 100%;
}}
img {{
    max-width: 100%;
    height: auto;
}}

.cover-image-box,
.hero-image-box {{
    max-width: 100%;
}}

.cover-bottom-table,
.bom-columns-table {{
    width: 100%;
    table-layout: fixed;
}}

.footer {{
    position: absolute;
    left: 0;
    bottom: -7mm;
    width: 100%;
    text-align: center;
    color: #666;
}}

.footer-line {{
    font-size: 6.5pt;
    line-height: 1.05;
}}

.section-kicker {{
    font-size: 8pt;
    font-weight: bold;
    text-transform: uppercase;
    color: #666;
    letter-spacing: 0.3px;
    margin-bottom: 1.5mm;
}}

.section-title {{
    font-size: 18pt;
    font-weight: bold;
    line-height: 1.05;
    margin-bottom: 2mm;
}}

.section-subtitle {{
    font-size: 9pt;
    color: #555;
    line-height: 1.2;
}}

.cover-shell {{
    height: 100%;
    display: block;
}}

.cover-topline {{
    font-size: 9pt;
    font-weight: bold;
    text-transform: uppercase;
    color: #777;
    letter-spacing: 0.6px;
    margin-bottom: 2mm;
}}

.debug-marker {{
    font-size: 11pt;
    font-weight: bold;
    color: #ff00aa;
    background: #fff59d;
    border: 0.4mm solid #ff00aa;
    display: inline-block;
    padding: 1mm 2mm;
    margin-bottom: 3mm;
}}

.cover-header-table,
.cover-bottom-table {{
    width: 100%;
    max-width: 100%;
    table-layout: fixed;
}}

.cover-header-table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}}

.cover-header-left {{
    width: 78%;
    vertical-align: top;
}}

.cover-header-right {{
    width: 22%;
    text-align: right;
    vertical-align: top;
}}

.cover-title {{
    font-size: 24pt;
    font-weight: 800;
    line-height: 1.00;
    margin-bottom: 1.2mm;
}}

.cover-subtitle {{
    font-size: 9.2pt;
    color: #555;
    line-height: 1.18;
}}

.cover-badge {{
    display: inline-block;
    padding: 2mm 3mm;
    border: 0.4mm solid #222;
    border-radius: 3mm;
    font-size: 8pt;
    font-weight: bold;
}}

.cover-stat-title {{
    font-size: 7.2pt;
    font-weight: 700;
    margin-bottom: 0.7mm;
    line-height: 1.05;
    color: #555
}}

.cover-stat-value {{
    font-size: 7.7pt;
    color: #555;
    line-height: 1.12;
}}

.cover-image-box {{
    margin: 7mm auto 0 auto;
    border: 0.5mm solid #D8D8D8;
    border-radius: 3mm;
    background: #FFF;
    height: 155mm;
    text-align: center;
    overflow: hidden;
    padding: 4mm;
}}

.cover-image-box img {{
    max-width: 100%;
    max-height: 100%;
    display: inline-block;
}}

.cover-bottom-table {{
    width: 100%;
    max-width: 100%;
    border-collapse: separate;
    border-spacing: 1.2mm 0;
    table-layout: fixed;
    margin-top: 6mm;
}}

.cover-tip-card {{
    width: 50%;
    background: #F7F7F7;
    border: 0.4mm solid #E1E1E1;
    border-radius: 3mm;
    padding: 3mm;
    vertical-align: top;
}}

.cover-tip-title {{
    font-size: 8pt;
    font-weight: bold;
    margin-bottom: 1.1mm;
}}

.cover-tip-text {{
    font-size: 7.7pt;
    color: #555;
    line-height: 1.25;
}}

.hero-image-box {{
    margin-top: 8mm;
    border: 0.5mm solid #D8D8D8;
    border-radius: 3mm;
    background: #FFF;
    height: 180mm;
    text-align: center;
    overflow: hidden;
    padding: 4mm;
}}

.hero-image-box img {{
    max-width: 100%;
    max-height: 100%;
    display: inline-block;
}}

.overview-note-box {{
    margin-top: 6mm;
    border: 0.45mm solid #DADADA;
    border-radius: 3mm;
    background: #F7F7F7;
    padding: 4mm;
}}

.overview-note-title {{
    font-size: 8.5pt;
    font-weight: bold;
    margin-bottom: 1.5mm;
}}

.overview-note-text {{
    font-size: 8pt;
    color: #555;
    line-height: 1.3;
}}

.index-box,
.inventory-box,
.legal-box {{
    border: 0.45mm solid #DADADA;
    border-radius: 3mm;
    background: #F7F7F7;
    padding: 3mm;
}}

.index-table,
.inventory-table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}}

.index-table thead th,
.inventory-table thead th {{
    font-size: 8pt;
    text-align: left;
    color: #666;
    border-bottom: 0.35mm solid #D8D8D8;
    padding: 1.5mm 1mm;
}}

.index-table tbody td,
.inventory-table tbody td {{
    border-bottom: 0.25mm solid #EBEBEB;
    padding: 1.5mm 1mm;
    vertical-align: middle;
    font-size: 7.2pt;
}}

.index-col-panel {{
    font-weight: bold;
}}

.index-col-parts {{
    color: #555;
}}

.index-col-page {{
    text-align: right;
    font-weight: bold;
}}

.inv-swatch {{
    width: 5mm;
    height: 5mm;
    border-radius: 50%;
    border: 0.25mm solid rgba(0,0,0,0.25);
    display: inline-block;
    vertical-align: middle;
}}

.inv-qty {{
    text-align: right;
    font-weight: bold;
}}

.muted {{
    color: #666;
}}

.panel-header-box {{
    margin-bottom: 4mm;
}}

.header-table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}}

.header-left {{
    width: 72%;
    vertical-align: top;
}}

.header-right {{
    width: 28%;
    vertical-align: top;
    text-align: right;
}}

.kicker {{
    font-size: 8pt;
    font-weight: bold;
    text-transform: uppercase;
    color: #666;
    margin-bottom: 1mm;
}}

.title {{
    font-size: 16pt;
    font-weight: bold;
    line-height: 1.05;
    margin-bottom: 1mm;
}}

.subtitle {{
    font-size: 8pt;
    color: #666;
}}

.meta {{
    font-size: 8pt;
    font-weight: bold;
    color: #666;
    padding-top: 2mm;
}}

.panel-bom-box {{
    border: 0.45mm solid #DADADA;
    border-radius: 3mm;
    background: #F7F7F7;
    padding: 3mm;
    height: 66mm;
    overflow: hidden;
    margin-bottom: 3mm;
}}

.panel-section-title {{
    font-size: 10pt;
    font-weight: bold;
    margin-bottom: 2mm;
}}

.bom-columns-table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 1mm 0;
    table-layout: fixed;
}}

.bom-column {{
    width: 25%;
    vertical-align: top;
}}

.bom-item {{
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    background: #FFF;
    border: none;
    border-radius: 2mm;
    margin-bottom: 1.4mm;
}}

.bom-item td {{
    vertical-align: middle;
    padding-top: 0.6mm;
    padding-bottom: 0.6mm;
}}

.bom-dot-cell {{
    width: 7mm;
    text-align: center;
}}

.bom-code-cell {{
    width: 10mm;
    font-size: 7pt;
    font-weight: bold;
    white-space: nowrap;
}}

.bom-name-cell {{
    width: auto;
    overflow: hidden;
}}

.bom-qty-cell {{
    width: 9mm;
    text-align: right;
    font-size: 8pt;
    font-weight: bold;
    white-space: nowrap;
    padding-right: 1.5mm;
}}

.color-dot {{
    width: 5mm;
    height: 5mm;
    border-radius: 50%;
    border: 0.25mm solid rgba(0,0,0,0.28);
    display: inline-block;
}}

.bom-name {{
    font-size: 6pt;
    font-weight: bold;
    line-height: 1.05;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.bom-sub {{
    font-size: 5pt;
    color: #666;
    line-height: 1.05;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.bom-empty {{
    height: 1mm;
}}

.grid-box {{
    border: 0.3mm solid #DDD;
    border-radius: 3mm;
    background: #FFF;
    padding: 2mm;
    height: 157mm;   /* garantisce 16 righe */
    overflow: hidden;
}}

.grid-title {{
    font-size: 8.5pt;
    font-weight: bold;
    margin-bottom: 2mm;
}}

.grid-table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}}

.grid-table th,
.grid-table td {{
    border: 0.25mm solid #C8C8C8;
    text-align: center;
    vertical-align: middle;
    padding: 0;
}}

.grid-corner {{
    width: 7mm;
    height: 7mm;
    background: #F2F2F2;
}}

.grid-col-head {{
    height: 6mm;
    background: #E6E6E6;
    font-size: 6pt;
    font-weight: bold;
    color: #333;
}}

.grid-row-head {{
    width: 6mm;
    background: #E6E6E6;
    font-size: 6pt;
    font-weight: bold;
    color: #333;
}}

.grid-cell {{
    height: 8.5mm;
    font-size: 5pt;
    font-weight: bold;
    line-height: 1;
}}

.legend-strip {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 2mm 0;
    table-layout: fixed;
    margin-top: 3mm;
}}

.legend-chip {{
    background: #F7F7F7;
    border: 0.3mm solid #E1E1E1;
    border-radius: 2mm;
    padding: 1.2mm 1.5mm;
    font-size: 6.5pt;
    font-weight: bold;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.legal-title {{
    font-size: 10pt;
    font-weight: bold;
    margin-bottom: 2mm;
}}

.legal-text {{
    font-size: 8pt;
    color: #555;
    line-height: 1.35;
}}

.blank-page-note {{
    padding-top: 100mm;
    text-align: center;
    color: #AAA;
    font-size: 10pt;
}}

</style>
</head>
<body>
{''.join(pages_html)}
</body>
</html>
"""


# =========================
# PDF BUILD
# =========================
def build_pdf_single_pass(page_specs, output_path):
    html = render_document(page_specs)
    HTML(string=html, base_url=str(JOB_PATH)).write_pdf(output_path)


def build_pdf_page_by_page(page_specs, output_path):
    if PdfWriter is None:
        log("⚠ pypdf non installato → fallback modalità standard (no progress reale sul render)")
        build_pdf_single_pass(page_specs, output_path)
        return

    temp_dir = Path(tempfile.mkdtemp(prefix="brixel_pdf_pages_"))
    total = len(page_specs)
    start_time = time.time()

    try:
        log(f"Render pagina per pagina: {total} pagine")
        temp_pdfs = []

        for idx, spec in enumerate(page_specs, start=1):
            single_html = render_document([spec])
            temp_pdf = temp_dir / f"page_{idx:04d}.pdf"

            HTML(string=single_html, base_url=str(JOB_PATH)).write_pdf(str(temp_pdf))
            temp_pdfs.append(temp_pdf)

            print_progress(idx, total, start_time, prefix="Render PDF ")

        finish_progress()
        log("Merge PDF...")

        writer = PdfWriter()
        for pdf_path in temp_pdfs:
            writer.append(str(pdf_path))

        with open(output_path, "wb") as f:
            writer.write(f)

        log(f"Merge completato: {output_path}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# =========================
# MAIN
# =========================
def main():
    total_start = time.time()
    log("=== START PDF GENERATION ===")

    t0 = time.time()
    data = generate_data()
    t1 = time.time()

    panel_count = len(data["panels"])
    total_rows, total_cols = get_total_panel_layout(data["grid"])

    log(f"Dati caricati in {t1 - t0:.2f}s")
    log(f"Pannelli trovati: {panel_count}")
    log(f"Layout pannelli: {total_rows} × {total_cols}")

    t2 = time.time()
    page_specs = build_page_specs(data)
    t3 = time.time()

    log(f"Pagine totali finali: {len(page_specs)}")
    log(f"Page specs generate in {t3 - t2:.2f}s")

    if ENABLE_LOG:
        build_pdf_page_by_page(page_specs, OUTPUT_PDF)
    else:
        build_pdf_single_pass(page_specs, OUTPUT_PDF)

    total_end = time.time()
    log(f"Tempo totale: {total_end - total_start:.2f}s")
    log("=== DONE ===")


if __name__ == "__main__":
    main()