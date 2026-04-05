from pathlib import Path
from weasyprint import HTML

OUTPUT_PDF = "demo_output.pdf"


def generate_mock_data():
    from PIL import Image, ImageDraw

    base_path = Path.home() / "demo_assets"
    base_path.mkdir(parents=True, exist_ok=True)

    path = base_path / "original.png"
    if not path.exists():
        img = Image.new("RGB", (1600, 1100), (210, 210, 210))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((20, 20, 1580, 1080), radius=24, fill=(206, 206, 206))
        img.save(path)

    return {
        "original": path.resolve().as_uri(),
    }


def render_html(data):
    from pathlib import Path

    assets = Path("/opt/assets")

    title_img = (assets / "title.png").resolve().as_uri()
    logo_img = (assets / "logo.png").resolve().as_uri()
    pippottino_img = (assets / "pippottino.png").resolve().as_uri()
    original_img = data["original"]

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
:root {{
  --accent-red: #ed1c24;
  --accent-orange: #ff7a00;
  --accent-yellow: #f2b705;
  --accent-blue: #4385f5;
}}

@page {{
    size: A4;
    margin: 0;
}}

body {{
    margin: 0;
}}

.page {{
    position: relative;
    width: 210mm;
    height: 297mm;
    background: #ffffff;
    font-family: Arial;
}}

.safe {{
    position: absolute;
    left: 11mm;
    top: 10mm;
    width: 188mm;
    height: 277mm;
    background: #ffffff;
    border-radius: 3mm;
    /*box-shadow: 0 0 5mm rgba(0,0,0,0.1);*/
}}

/* ---------------- TITLE ---------------- */

.title-image {{
    position: absolute;
    top: 8mm;
    left: 50%;
    transform: translateX(-50%);
    width: 112mm;   /* ridotto ~25% */
}}

.gradient-text {{
  background: linear-gradient(90deg, var(--accent-red) 0%, var(--accent-orange) 28%, var(--accent-yellow) 54%, var(--accent-blue) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}}

/* ---------------- SUBTITLE ---------------- */

.subtitle {{
    position: absolute;
    top: 36mm;
    left: 0;
    font-size: 6mm;
    color: #111;
}}

.brand-text {{
  font-size: 20px;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1;
  white-space: nowrap;
}}

/* ---------------- IMAGE BOX ---------------- */

.image-card {{
    position: absolute;
    top: 55mm;
    left: 0;
    width: 188mm;
    height: 146mm;
    background: #d8d8d8;
    border-radius: 4mm;
    overflow: hidden;
}}

.image-card img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: 0.18;
}}

.image-label {{
    position: absolute;
    top: 5mm;
    left: 6mm;
    font-size: 3.5mm;
    color: rgba(255,255,255,0.8);
}}

/* ---------------- CHARACTER ---------------- */

.worker {{
    position: absolute;
    top: 135mm;
    right: 75%;
    width: 105mm;
}}

/* ---------------- LOGO ---------------- */

.brand-logo {{
    position: absolute;
    top: 225mm;
    left: 50%;
    transform: translateX(-50%);
    width: 95mm;
}}

/* ---------------- FOOTER ---------------- */

.footer {{
    position: absolute;
    bottom: -2mm;  /* abbassato ~1cm */
    left: 0;
    font-size: 2.3mm;  /* -25% */
    color: #666;
    line-height: 1.3;
}}

</style>
</head>

<body>

<div class="page">
    <div class="safe">

        <!-- TITLE -->
        <img src="{title_img}" class="title-image">

        <!-- SUBTITLE -->
        <div class="subtitle gradient-text">Istruzioni Brixel Art</div>
        <span class="brand-text gradient-text">Brixel my pic!</span>

        <!-- IMAGE -->
        <div class="image-card">
            <div class="image-label">Originale</div>
            <img src="{original_img}">
        </div>

        <!-- CHARACTER -->
        <img src="{pippottino_img}" class="worker">

        <!-- LOGO -->
        <img src="{logo_img}" class="brand-logo">

        <!-- FOOTER -->
        <div class="footer">
            © 2026 LeoBrick di Graziano Luca & Co<br>
            Powered by ABR Dome Software House<br>
            https://www.leobrick.com
        </div>

    </div>
</div>
</body>
</html>
"""


def build_pdf(data, output_path):
    html = render_html(data)
    HTML(string=html, base_url="/opt").write_pdf(output_path)


def main():
    print("Generating PDF...")
    data = generate_mock_data()
    build_pdf(data, OUTPUT_PDF)
    print(f"Done: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()