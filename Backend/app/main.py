from __future__ import annotations

import io
import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image, UnidentifiedImageError
Image.MAX_IMAGE_PIXELS = 10_000_000  # 🔥 anti decompression bomb
from starlette.middleware.cors import CORSMiddleware

from .schemas import (
    ConfirmPaymentResponse,
    PaymentConfirmRequest,
    PreparePackageResponse,
    RedeemRequest,
)
from .services.core_adapter import (
    generate_package_from_bytes,
    generate_preview_from_bytes,
    normalize_params,
)
from .settings import settings
from .storage import Storage
from .utils import generate_public_code, generate_redeem_token, utc_timestamp


# ------------------ LOGGING ------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("leobrick")


# ------------------ APP ------------------

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://(.*\.)?leobrick\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = Storage()


# ================== 🆕 REQUEST LOGGING ==================

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:10]
    start = time.perf_counter()

    logger.info(
        "➡️ %s %s rid=%s content_length=%s content_type=%s origin=%s",
        request.method,
        request.url.path,
        request_id,
        request.headers.get("content-length"),
        request.headers.get("content-type"),
        request.headers.get("origin"),
    )

    try:
        response = await call_next(request)
    except Exception:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.exception("💥 Crash request rid=%s elapsed_ms=%s", request_id, elapsed)
        raise

    elapsed = int((time.perf_counter() - start) * 1000)

    response.headers["X-Request-ID"] = request_id

    logger.info(
        "⬅️ %s %s rid=%s status=%s elapsed_ms=%s",
        request.method,
        request.url.path,
        request_id,
        response.status_code,
        elapsed,
    )

    return response


# ------------------ HELPERS ------------------

def _error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def _safe_params_for_log(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "width": params.get("width"),
        "height": params.get("height"),
        "piece_type": params.get("piece_type"),
        "max_colors": params.get("max_colors"),
        "resize_mode": params.get("resize_mode"),
        "panel_rounding": params.get("panel_rounding"),
        "dither": params.get("dither"),
        "generate_pdf": params.get("generate_pdf"),
        "generate_stud_preview": params.get("generate_stud_preview"),
        "piece_aware_palette": params.get("piece_aware_palette"),
    }


async def _read_image(file: UploadFile) -> bytes:
    if not file.filename:
        raise _error(400, "File immagine mancante.")

    original_content_type = (file.content_type or "").lower()
    image_bytes = await file.read()
    await file.seek(0)

    logger.info(
        "📥 Upload ricevuto: filename=%s content_type=%s bytes=%d",
        file.filename,
        original_content_type,
        len(image_bytes),
    )
    
    # 🔥 LIMITE HARD (anti-OOM)
    if len(image_bytes) > 2_000_000:  # ~2MB
        logger.warning("❌ File troppo grande: %d bytes", len(image_bytes))
        raise _error(413, "File troppo grande (max 2MB).")

    if not image_bytes:
        raise _error(400, "Il file caricato è vuoto.")

    if len(image_bytes) > settings.max_upload_bytes:
        raise _error(
            413,
            f"Il file supera il limite di {settings.max_upload_bytes // (1024 * 1024)} MB."
        )

    try:
        img = Image.open(io.BytesIO(image_bytes))

        # 🔥 BLOCCO PRIMA DI LOAD (NON USA RAM)
        w, h = img.size

        if w * h > 5_000_000:  # ~5MP
            logger.warning("❌ Immagine troppo grande: %sx%s", w, h)
            raise _error(413, "Immagine troppo grande.")

        img.load()

        logger.info(
            "🖼️ Immagine aperta: format=%s mode=%s size=%s info_keys=%s",
            img.format,
            img.mode,
            img.size,
            sorted(list(img.info.keys())),
        )

        if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
            background = Image.new("RGBA", img.size, (255, 255, 255, 255))
            img = Image.alpha_composite(background, img.convert("RGBA")).convert("RGB")
            logger.info("🎨 Trasparenza appiattita su sfondo bianco")
        else:
            if img.mode != "RGB":
                img = img.convert("RGB")
                logger.info("🔧 Convertita in RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        normalized_bytes = buffer.getvalue()

        logger.info(
            "✅ Immagine normalizzata: output_bytes=%d mode=%s size=%s",
            len(normalized_bytes),
            img.mode,
            img.size,
        )

        return normalized_bytes

    except UnidentifiedImageError:
        logger.error("❌ Formato immagine non riconosciuto: %s", file.filename)
        raise _error(400, "Formato immagine non riconosciuto.")
    except Exception:
        logger.exception("❌ Errore processing immagine: filename=%s", file.filename)
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
    
    # 🔥 HARD LIMIT BACKEND (NON BYPASSABILE)
    try:
        w = int(params.get("width") or 0)
        h = int(params.get("height") or 0)

        if w > 512 or h > 512:
            logger.warning("❌ Dimensioni troppo grandi: %sx%s", w, h)
            raise _error(400, "Dimensioni troppo grandi (max 512).")
        
        if w * h > 300_000:
            logger.warning("❌ Preview area troppo grande: %sx%s", w, h)
            raise _error(400, "Area troppo grande.")

    except ValueError:
        raise _error(400, "Parametri dimensione non validi.")

    logger.info("🧩 Parametri preview: %s", _safe_params_for_log(params))

    try:
        preview_bytes, meta = generate_preview_from_bytes(image_bytes, params)
        logger.info(
            "✅ Preview generata: preview_bytes=%d meta=%s",
            len(preview_bytes),
            meta,
        )
    except Exception:
        logger.exception(
            "💥 Errore in generate_preview_from_bytes con params=%s",
            _safe_params_for_log(params),
        )
        raise _error(500, "Errore durante la generazione della preview.")

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

    # 🔥 HARD LIMIT BACKEND (ANTI-OOM)
    try:
        w = int(params.get("width") or 0)
        h = int(params.get("height") or 0)

        if w > 512 or h > 512:
            logger.warning("❌ Package troppo grande: %sx%s", w, h)
            raise _error(400, "Dimensioni troppo grandi (max 512).")

        # 🔥 EXTRA SICUREZZA (consigliato)
        if w * h > 300_000:
            logger.warning("❌ Area troppo grande: %sx%s", w, h)
            raise _error(400, "Area troppo grande.")

    except ValueError:
        raise _error(400, "Parametri dimensione non validi.")

    logger.info("🧩 Parametri package: %s", _safe_params_for_log(params))

    code = generate_public_code()
    job_dir = storage.ensure_job_dir(code)

    logger.info("📁 Job dir creato/trovato: code=%s dir=%s", code, job_dir)

    try:
        package_meta = generate_package_from_bytes(image_bytes, params, job_dir)
        logger.info("✅ Package generato: code=%s meta=%s", code, package_meta)
    except Exception:
        logger.exception(
            "💥 Errore in generate_package_from_bytes: code=%s dir=%s params=%s",
            code,
            job_dir,
            _safe_params_for_log(params),
        )
        raise _error(500, "Errore durante la generazione del pacchetto.")

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

    try:
        storage.save_metadata(code, metadata)
        logger.info("💾 Metadata salvati: code=%s", code)
    except Exception:
        logger.exception("💥 Errore salvataggio metadata: code=%s", code)
        raise _error(500, "Errore durante il salvataggio dei metadata.")

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
    logger.info("📄 Metadata path confirm-payment: %s", meta_path)

    if not meta_path.exists():
        logger.warning("❌ Codice non trovato: %s", payload.code)
        raise _error(404, "Codice non trovato")

    try:
        metadata = storage.load_metadata(payload.code)
        logger.info("📖 Metadata caricati per %s: %s", payload.code, metadata)
    except Exception:
        logger.exception("💥 Errore load_metadata per %s", payload.code)
        raise _error(500, "Errore lettura metadata.")

    if metadata.get("status") == "paid" and metadata.get("redeem_token"):
        logger.info("ℹ️ Codice già pagato: %s", payload.code)
        return ConfirmPaymentResponse(
            redeem_token=metadata["redeem_token"],
            status="paid",
        )

    token = generate_redeem_token()

    metadata["redeem_token"] = token
    metadata["status"] = "paid"

    try:
        storage.save_metadata(payload.code, metadata)
    except Exception:
        logger.exception("💥 Errore salvataggio metadata dopo pagamento: %s", payload.code)
        raise _error(500, "Errore aggiornamento metadata.")

    logger.info("✅ Pagamento confermato per %s", payload.code)

    return ConfirmPaymentResponse(redeem_token=token)


@app.post("/api/redeem")
def redeem(payload: RedeemRequest):
    logger.info("🎟️ Redeem token ricevuto: %s", payload.token)

    try:
        code, metadata = storage.find_by_token(payload.token)
        logger.info("🔎 Risultato find_by_token: code=%s metadata=%s", code, metadata)
    except Exception:
        logger.exception("💥 Errore find_by_token")
        raise _error(500, "Errore ricerca token.")

    if not code or metadata.get("status") != "paid":
        logger.warning("❌ Token non valido")
        raise _error(403, "Token non valido")

    zip_path = storage.zip_path(code)
    logger.info("🗜️ ZIP path: %s", zip_path)

    if not zip_path.exists():
        logger.error("❌ ZIP mancante per %s", code)
        raise _error(404, "Pacchetto non trovato")

    logger.info("⬇️ Download pronto per %s", code)

    return FileResponse(zip_path, media_type="application/zip", filename=f"{code}.zip")


@app.get("/api/download/{public_code}")
def download(public_code: str):
    logger.info("⬇️ Download diretto: %s", public_code)

    zip_path = storage.zip_path(public_code)
    logger.info("🗜️ ZIP path download diretto: %s", zip_path)

    if not zip_path.exists():
        logger.warning("❌ Pacchetto non trovato per download diretto: %s", public_code)
        raise _error(404, "Pacchetto non trovato")

    return FileResponse(zip_path, media_type="application/zip", filename=f"{public_code}.zip")