from __future__ import annotations

import logging
import io
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError

from .schemas import ConfirmPaymentResponse, PaymentConfirmRequest, PreparePackageResponse, RedeemRequest
from .services.core_adapter import generate_package_from_bytes, generate_preview_from_bytes, normalize_params
from .settings import settings
from .storage import Storage
from .utils import generate_public_code, generate_redeem_token, utc_timestamp


# ------------------ LOGGING ------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

logger = logging.getLogger("leobrick")


# ------------------ APP ------------------

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = Storage()


# ------------------ HELPERS ------------------

def _error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


async def _read_image(file: UploadFile) -> bytes:
    if not file.filename:
        raise _error(400, "File immagine mancante.")

    image_bytes = await file.read()
    await file.seek(0)

    logger.info("📥 Upload ricevuto: %s (%d bytes)", file.filename, len(image_bytes))

    if not image_bytes:
        raise _error(400, "Il file caricato è vuoto.")

    if len(image_bytes) > settings.max_upload_bytes:
        raise _error(
            413,
            f"Il file supera il limite di {settings.max_upload_bytes // (1024 * 1024)} MB."
        )

    try:
        img = Image.open(io.BytesIO(image_bytes))

        # 🔥 forza decoding completo (fix PNG strani)
        img.load()

        logger.info("🖼️ Immagine aperta: mode=%s size=%s", img.mode, img.size)

        # 🔥 normalizzazione robusta
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
            logger.info("🔧 Convertita in RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)

        return buffer.getvalue()

    except UnidentifiedImageError:
        logger.error("❌ Formato immagine non riconosciuto: %s", file.filename)
        raise _error(400, "Formato immagine non riconosciuto.")

    except Exception as e:
        logger.exception("❌ Errore processing immagine")
        raise _error(400, "Immagine non valida o corrotta.")


def _collect_form_params(form: dict[str, Any]) -> dict[str, Any]:
    return {
        "width": form.get("width"),
        "height": form.get("height"),
        "piece_type": form.get("piece_type"),
        "max_colors": form.get("max_colors"),
        "resize_mode": form.get("resize_mode"),
        "panel_rounding": form.get("panel_rounding"),
        "dither": form.get("dither"),
        "generate_pdf": form.get("generate_pdf"),
        "generate_stud_preview": form.get("generate_stud_preview"),
        "piece_aware_palette": form.get("piece_aware_palette"),
    }


# ------------------ ERROR HANDLER ------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    logger.exception("💥 Errore inatteso su %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Errore interno del server."})


# ------------------ ROUTES ------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/preview")
async def preview(
    file: UploadFile = File(...),
    width: str = Form(...),
    height: str | None = Form(None),
    piece_type: str = Form("tile_1x1_square"),
    max_colors: str | None = Form(None),
    resize_mode: str = Form("contain"),
    panel_rounding: str = Form("nearest"),
    dither: str = Form("on"),
    generate_pdf: str = Form("off"),
    generate_stud_preview: str = Form("on"),
    piece_aware_palette: str = Form("on"),
):
    logger.info("⚙️ Preview richiesta")

    image_bytes = await _read_image(file)
    params = _collect_form_params(locals())

    preview_bytes, _meta = generate_preview_from_bytes(image_bytes, params)

    logger.info("✅ Preview generata")

    return Response(content=preview_bytes, media_type="image/png")


@app.post("/api/prepare-package", response_model=PreparePackageResponse)
async def prepare_package(
    file: UploadFile = File(...),
    width: str = Form(...),
    height: str | None = Form(None),
    piece_type: str = Form("tile_1x1_square"),
    max_colors: str | None = Form(None),
    resize_mode: str = Form("contain"),
    panel_rounding: str = Form("nearest"),
    dither: str = Form("on"),
    generate_pdf: str = Form("on"),
    generate_stud_preview: str = Form("on"),
    piece_aware_palette: str = Form("on"),
):
    logger.info("📦 Generazione package richiesta")

    image_bytes = await _read_image(file)
    params = _collect_form_params(locals())

    code = generate_public_code()
    job_dir = storage.ensure_job_dir(code)

    logger.info("📁 Job dir: %s", job_dir)

    package_meta = generate_package_from_bytes(image_bytes, params, job_dir)

    metadata = {
        "public_code": code,
        "redeem_token": None,
        "status": "pending",
        "params": normalize_params(params),
        "width": package_meta["width"],
        "height": package_meta["height"],
        "piece_type": package_meta["piece_type"],
        "palette_size": package_meta["palette_size"],
        "created_at": utc_timestamp(),
        "files": package_meta["files"],
    }

    storage.save_metadata(code, metadata)

    logger.info("✅ Package pronto per %s", code)

    return PreparePackageResponse(code=code)


@app.post("/api/confirm-payment", response_model=ConfirmPaymentResponse)
def confirm_payment(payload: PaymentConfirmRequest, request: Request):
    logger.info("💳 Confirm payment per %s", payload.code)

    api_key = request.headers.get("X-API-KEY")

    if api_key != settings.internal_api_key:
        logger.warning("❌ API KEY non valida")
        raise _error(403, "Unauthorized")

    meta_path = storage.metadata_path(payload.code)

    if not meta_path.exists():
        logger.warning("❌ Codice non trovato: %s", payload.code)
        raise _error(404, "Codice non trovato")

    metadata = storage.load_metadata(payload.code)

    if metadata.get("status") == "paid" and metadata.get("redeem_token"):
        return ConfirmPaymentResponse(
            redeem_token=metadata["redeem_token"],
            status="paid"
        )

    token = generate_redeem_token()

    metadata["redeem_token"] = token
    metadata["status"] = "paid"

    storage.save_metadata(payload.code, metadata)

    logger.info("✅ Pagamento confermato per %s", payload.code)

    return ConfirmPaymentResponse(redeem_token=token)


@app.post("/api/redeem")
def redeem(payload: RedeemRequest):
    logger.info("🎟️ Redeem token: %s", payload.token)

    code, metadata = storage.find_by_token(payload.token)

    if not code or metadata.get("status") != "paid":
        logger.warning("❌ Token non valido")
        raise _error(403, "Token non valido")

    zip_path = storage.zip_path(code)

    if not zip_path.exists():
        logger.error("❌ ZIP mancante per %s", code)
        raise _error(404, "Pacchetto non trovato")

    logger.info("⬇️ Download pronto per %s", code)

    return FileResponse(zip_path, media_type="application/zip", filename=f"{code}.zip")


@app.get("/api/download/{public_code}")
def download(public_code: str):
    logger.info("⬇️ Download diretto: %s", public_code)

    zip_path = storage.zip_path(public_code)

    if not zip_path.exists():
        raise _error(404, "Pacchetto non trovato")

    return FileResponse(zip_path, media_type="application/zip", filename=f"{public_code}.zip")