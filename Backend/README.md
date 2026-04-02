LeoBrick backend + core unificati

Questo pacchetto contiene il backend FastAPI con il core LEGO integrato direttamente in `app/core_vendor/lego_mosaic_pro`.

Avvio:
1. python -m venv .venv
2. source .venv/bin/activate  (Windows: .venv\Scripts\activate)
3. pip install -r requirements.txt
4. uvicorn main:app --host 0.0.0.0 --port 8000

Endpoint:
- POST /api/preview
- POST /api/prepare-package
- POST /api/confirm-payment
- POST /api/redeem
- POST /api/generate  (compatibilità frontend legacy)
- GET /api/download/{public_code}
- GET /health

Storage:
storage/jobs/LEO-XXXXXX/
  output.zip
  metadata.json

Note:
- /api/confirm-payment può essere chiamato manualmente oppure da un futuro webhook PayPal.
- Il core usato dal backend è quello incluso in `app/core_vendor/lego_mosaic_pro`.
