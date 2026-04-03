import logging
import os

from app.settings import settings
from app.storage import Storage
from app.utils import generate_redeem_token

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters


# ------------------ LOGGING ------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

logger = logging.getLogger("leobrick.bot")


# ------------------ CONFIG ------------------

BOT_TOKEN = settings.telegram_bot_token
ALLOWED_USERS = set(settings.telegram_allowed_users)

storage = Storage()


# ------------------ CORE LOGIC ------------------

def confirm_payment_internal(code: str):
    meta_path = storage.metadata_path(code)

    logger.info("Checking path: %s", meta_path)

    if not meta_path.exists():
        parent = meta_path.parent

        if parent.exists():
            logger.info("Contenuto directory %s: %s", parent, os.listdir(parent))
        else:
            logger.warning("Directory parent NON esiste: %s", parent)

        logger.error("Codice non trovato: %s", meta_path)
        raise Exception(f"Codice non trovato: {code}")

    metadata = storage.load_metadata(code)
    logger.info("Metadata caricati: %s", metadata)

    if metadata.get("status") == "paid" and metadata.get("redeem_token"):
        logger.info("Token già esistente per %s", code)
        return metadata["redeem_token"]

    token = generate_redeem_token()

    metadata["redeem_token"] = token
    metadata["status"] = "paid"

    storage.save_metadata(code, metadata)

    logger.info("Pagamento manuale confermato per %s", code)

    return token


# ------------------ HANDLERS ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Comando /start ricevuto")

    await update.message.reply_text(
        "🤖 LeoBrick Bot attivo\n\nInvia un codice LEO-XXXX"
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("UPDATE ricevuto")

    if not update.message:
        logger.warning("NO MESSAGE")
        return

    if not update.message.text:
        logger.warning("NO TEXT")
        return

    user_id = update.effective_user.id
    logger.info("USER: %s", user_id)

    raw_text = update.message.text.strip()
    logger.info("TEXT ricevuto: %s", raw_text)

    # 🔥 estrazione codice LEO-XXXX (funziona con comandi e gruppi)
    parts = raw_text.split()

    code = None
    for part in parts:
        if part.upper().startswith("LEO-"):
            code = part.upper()
            break

    if not code:
        await update.message.reply_text("❌ Inserisci un codice valido (LEO-XXXX)")
        return

    logger.info("Codice estratto: %s", code)

    if user_id not in ALLOWED_USERS:
        logger.warning("USER NON AUTORIZZATO: %s", user_id)
        return

    msg = await update.message.reply_text("⏳ Genero token...")

    try:
        token = confirm_payment_internal(code)

        await msg.edit_text(
            f"✅ TOKEN GENERATO\n\n"
            f"Codice: {code}\n"
            f"RDM:\n{token}"
        )

    except Exception as e:
        logger.error("Errore: %s", str(e))
        await msg.edit_text(f"❌ Errore: {str(e)}")


# ------------------ START BOT ------------------

def start_bot():
    logger.info("Avvio bot Telegram...")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT, handle))

    logger.info("🤖 Bot Telegram avviato")

    application.run_polling()