from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .cli import DEFAULT_CATALOG, DEFAULT_OWNED, DEFAULT_PALETTE, PIECE_CHOICES
from .core import MosaicConfig, generate_mosaic


PRESETS = {
    "Ritratto": {"crop_mode": "fill", "contrast": 1.12, "saturation": 0.90, "sharpen": 1.12},
    "Paesaggio": {"crop_mode": "fit", "contrast": 1.05, "saturation": 1.00, "sharpen": 1.05},
    "Logo": {"crop_mode": "stretch", "contrast": 1.20, "saturation": 1.05, "sharpen": 1.20},
}


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LEGO Mosaic Pro Final")
        self.geometry("980x760")
        self.minsize(900, 680)
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.cwd() / "output"))
        self.palette_var = tk.StringVar(value=str(DEFAULT_PALETTE))
        self.catalog_var = tk.StringVar(value=str(DEFAULT_CATALOG))
        self.owned_var = tk.StringVar(value=str(DEFAULT_OWNED))
        self.width_var = tk.IntVar(value=128)
        self.height_var = tk.IntVar(value=0)
        self.panel_var = tk.IntVar(value=16)
        self.max_colors_var = tk.IntVar(value=0)
        self.current_only_var = tk.BooleanVar(value=True)
        self.dither_var = tk.BooleanVar(value=True)
        self.pdf_var = tk.BooleanVar(value=True)
        self.stud_var = tk.BooleanVar(value=True)
        self.costing_var = tk.BooleanVar(value=True)
        self.piece_aware_var = tk.BooleanVar(value=True)
        self.preset_var = tk.StringVar(value="Ritratto")
        self.piece_var = tk.StringVar(value="tile_1x1_square")
        self.status_var = tk.StringVar(value="Pronto")
        self.generate_button: ttk.Button | None = None
        self._build()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 6}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Immagine input").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.input_var, width=78).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Sfoglia", command=self.pick_input).grid(row=0, column=2, **pad)
        ttk.Label(frm, text="Cartella output").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.output_var, width=78).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Sfoglia", command=self.pick_output).grid(row=1, column=2, **pad)
        ttk.Label(frm, text="Palette XML").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.palette_var, width=78).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Sfoglia", command=self.pick_palette).grid(row=2, column=2, **pad)
        ttk.Label(frm, text="Catalogo pezzi").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.catalog_var, width=78).grid(row=3, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Sfoglia", command=self.pick_catalog).grid(row=3, column=2, **pad)
        ttk.Label(frm, text="Inventario posseduto").grid(row=4, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.owned_var, width=78).grid(row=4, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Sfoglia", command=self.pick_owned).grid(row=4, column=2, **pad)
        ttk.Separator(frm).grid(row=5, column=0, columnspan=3, sticky="ew", padx=8, pady=12)

        row_cfg = ttk.Frame(frm)
        row_cfg.grid(row=6, column=0, columnspan=3, sticky="ew", padx=8)
        for i in range(12):
            row_cfg.columnconfigure(i, weight=1)
        ttk.Label(row_cfg, text="Preset").grid(row=0, column=0, sticky="w", **pad)
        ttk.Combobox(row_cfg, textvariable=self.preset_var, values=list(PRESETS.keys()), state="readonly", width=14).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(row_cfg, text="Pezzo").grid(row=0, column=2, sticky="e", **pad)
        ttk.Combobox(row_cfg, textvariable=self.piece_var, values=list(PIECE_CHOICES.keys()), state="readonly", width=18).grid(row=0, column=3, sticky="w", **pad)
        ttk.Label(row_cfg, text="Larghezza").grid(row=0, column=4, sticky="e", **pad)
        ttk.Entry(row_cfg, textvariable=self.width_var, width=8).grid(row=0, column=5, sticky="w", **pad)
        ttk.Label(row_cfg, text="Altezza (0=auto)").grid(row=0, column=6, sticky="e", **pad)
        ttk.Entry(row_cfg, textvariable=self.height_var, width=8).grid(row=0, column=7, sticky="w", **pad)
        ttk.Label(row_cfg, text="Pannello").grid(row=0, column=8, sticky="e", **pad)
        ttk.Entry(row_cfg, textvariable=self.panel_var, width=8).grid(row=0, column=9, sticky="w", **pad)
        ttk.Label(row_cfg, text="Max colori (0=nessun limite)").grid(row=0, column=10, sticky="e", **pad)
        ttk.Entry(row_cfg, textvariable=self.max_colors_var, width=8).grid(row=0, column=11, sticky="w", **pad)

        opts = ttk.LabelFrame(frm, text="Opzioni")
        opts.grid(row=7, column=0, columnspan=3, sticky="ew", padx=8, pady=10)
        ttk.Checkbutton(opts, text="Solo colori attuali", variable=self.current_only_var).grid(row=0, column=0, sticky="w", **pad)
        ttk.Checkbutton(opts, text="Dithering", variable=self.dither_var).grid(row=0, column=1, sticky="w", **pad)
        ttk.Checkbutton(opts, text="PDF istruzioni", variable=self.pdf_var).grid(row=0, column=2, sticky="w", **pad)
        ttk.Checkbutton(opts, text="Preview stud", variable=self.stud_var).grid(row=0, column=3, sticky="w", **pad)
        ttk.Checkbutton(opts, text="Stima costi", variable=self.costing_var).grid(row=0, column=4, sticky="w", **pad)
        ttk.Checkbutton(opts, text="Palette compatibile col pezzo", variable=self.piece_aware_var).grid(row=0, column=5, sticky="w", **pad)

        help_box = ttk.LabelFrame(frm, text="Output principali")
        help_box.grid(row=8, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        msg = (
            "• mosaic.png\n"
            "• preview_pixel.png / preview_stud.png / overview.png\n"
            "• inventory.csv / grid.csv / panel_inventory.csv\n"
            "• purchase_plan.csv / piece_compatibility.csv / cost_summary.txt\n"
            "• instructions.pdf / instructions.html\n"
            "• bricklink_wanted_list.xml / report.json\n"
            "• instructions/panel_XX_YY.png + legend.csv\n\n"
            "La palette può essere limitata al numero massimo di colori e ai colori realmente disponibili per il pezzo scelto."
        )
        ttk.Label(help_box, text=msg, justify="left").pack(anchor="w", padx=10, pady=10)

        bottom = ttk.Frame(frm)
        bottom.grid(row=9, column=0, columnspan=3, sticky="ew", padx=8, pady=12)
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.generate_button = ttk.Button(bottom, text="Genera mosaico", command=self.run)
        self.generate_button.grid(row=0, column=1, padx=8)
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(8, weight=1)

    def pick_input(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Immagini", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if path:
            self.input_var.set(path)

    def pick_output(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)

    def pick_palette(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("XML", "*.xml")])
        if path:
            self.palette_var.set(path)

    def pick_catalog(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if path:
            self.catalog_var.set(path)

    def pick_owned(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if path:
            self.owned_var.set(path)

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self.status_var.set(text))

    def _toggle_generate_button(self, enabled: bool) -> None:
        def cb() -> None:
            if self.generate_button is not None:
                self.generate_button.configure(state=("normal" if enabled else "disabled"))
        self.after(0, cb)

    def _show_info(self, title: str, message: str) -> None:
        self.after(0, lambda: messagebox.showinfo(title, message))

    def _show_error(self, title: str, message: str) -> None:
        self.after(0, lambda: messagebox.showerror(title, message))

    def _build_config(self) -> MosaicConfig:
        width = self.width_var.get()
        height = self.height_var.get() or None
        panel_size = self.panel_var.get()
        max_colors = self.max_colors_var.get() or None
        if width <= 0:
            raise ValueError("La larghezza deve essere maggiore di zero.")
        if panel_size <= 0:
            raise ValueError("La dimensione del pannello deve essere maggiore di zero.")
        if max_colors is not None and max_colors <= 0:
            raise ValueError("Il massimo numero di colori deve essere maggiore di zero.")
        preset = PRESETS[self.preset_var.get()]
        piece_type = self.piece_var.get()
        if piece_type not in PIECE_CHOICES:
            raise ValueError("Tipo di pezzo non valido.")
        return MosaicConfig(
            width=width,
            height=height,
            panel_size=panel_size,
            current_only=self.current_only_var.get(),
            dither=self.dither_var.get(),
            crop_mode=preset["crop_mode"],
            contrast=preset["contrast"],
            saturation=preset["saturation"],
            sharpen=preset["sharpen"],
            generate_pdf=self.pdf_var.get(),
            generate_stud_preview=self.stud_var.get(),
            piece_type=piece_type,
            part_name=PIECE_CHOICES[piece_type],
            catalog_path=self.catalog_var.get().strip() if self.costing_var.get() else None,
            owned_inventory_path=self.owned_var.get().strip() if self.costing_var.get() and self.owned_var.get().strip() else None,
            piece_aware_palette=self.piece_aware_var.get(),
            max_colors=max_colors,
        )

    def run(self) -> None:
        input_path = self.input_var.get().strip()
        if not input_path:
            messagebox.showerror("Errore", "Seleziona un'immagine di input.")
            return
        self._toggle_generate_button(False)

        def worker() -> None:
            try:
                self._set_status("Generazione in corso...")
                cfg = self._build_config()
                result = generate_mosaic(input_path, self.palette_var.get().strip(), self.output_var.get().strip(), cfg)
                extra = f"\nStima costo: EUR {result.get('estimated_cost_eur', 'n/d')}"
                extra += f"\nHTML istruzioni: {result.get('instructions_html', '')}"
                extra += f"\nWanted list XML: {result.get('bricklink_wanted_list', 'n/d')}"
                self._set_status(f"Completato: {result['mosaic']}")
                self._show_info("Completato", f"Mosaico generato in:\n{self.output_var.get().strip()}{extra}")
            except Exception as exc:
                self._set_status("Errore")
                self._show_error("Errore", str(exc))
            finally:
                self._toggle_generate_button(True)

        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
