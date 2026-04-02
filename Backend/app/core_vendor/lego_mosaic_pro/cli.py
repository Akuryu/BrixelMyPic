from __future__ import annotations

import argparse
from pathlib import Path

from .core import MosaicConfig, generate_mosaic


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PALETTE = BASE_DIR / "palettes" / "current_solid_lego.xml"
DEFAULT_CATALOG = BASE_DIR / "assets" / "piece_catalog.csv"
DEFAULT_OWNED = BASE_DIR / "assets" / "sample_owned_inventory.csv"
PIECE_CHOICES = {
    "tile_1x1_square": "Tile 1x1",
    "tile_1x1_round": "Tile 1x1 Round",
    "plate_1x1_round": "Plate 1x1 Round",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LEGO Mosaic Pro Final - converte immagini in mosaici LEGO multipli di 16x16")
    parser.add_argument("input_image", help="Immagine di input")
    parser.add_argument("--output-dir", default="output", help="Cartella di output")
    parser.add_argument("--palette", default=str(DEFAULT_PALETTE), help="File XML palette")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="Catalogo locale pezzi/colori")
    parser.add_argument("--owned-inventory", default=str(DEFAULT_OWNED), help="CSV opzionale con pezzi posseduti")
    parser.add_argument("--piece-type", choices=list(PIECE_CHOICES), default="tile_1x1_square", help="Tipo di pezzo per stima costi e compatibilità")
    parser.add_argument("--width", type=int, required=True, help="Larghezza in stud")
    parser.add_argument("--height", type=int, default=None, help="Altezza in stud")
    parser.add_argument("--panel-size", type=int, default=16, help="Dimensione pannello")
    parser.add_argument("--crop-mode", choices=["fit", "fill", "stretch"], default="fit")
    parser.add_argument("--max-colors", type=int, default=None, help="Limita il numero massimo di colori usati")
    parser.add_argument("--no-current-only", action="store_true", help="Permette anche colori non marcati come current")
    parser.add_argument("--no-dither", action="store_true")
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--no-stud-preview", action="store_true")
    parser.add_argument("--no-costing", action="store_true")
    parser.add_argument("--disable-piece-aware-palette", action="store_true", help="Non restringe la palette ai colori disponibili per il pezzo scelto")
    parser.add_argument("--contrast", type=float, default=1.08)
    parser.add_argument("--saturation", type=float, default=0.95)
    parser.add_argument("--sharpen", type=float, default=1.05)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    piece_type = args.piece_type
    cfg = MosaicConfig(
        width=args.width,
        height=args.height,
        panel_size=args.panel_size,
        current_only=not args.no_current_only,
        dither=not args.no_dither,
        crop_mode=args.crop_mode,
        contrast=args.contrast,
        saturation=args.saturation,
        sharpen=args.sharpen,
        generate_pdf=not args.no_pdf,
        generate_stud_preview=not args.no_stud_preview,
        piece_type=piece_type,
        part_name=PIECE_CHOICES[piece_type],
        catalog_path=None if args.no_costing else args.catalog,
        owned_inventory_path=None if args.no_costing else args.owned_inventory,
        piece_aware_palette=not args.disable_piece_aware_palette,
        max_colors=args.max_colors,
    )
    result = generate_mosaic(args.input_image, args.palette, args.output_dir, cfg)
    print("Generazione completata.")
    for key, value in result.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
