from app.settings import settings
from app.storage import Storage
from app.utils import generate_redeem_token

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

import logging

logger = logging.getLogger("leobrick.bot")

BOT_TOKEN = settings.telegram_bot_token
ALLOWED_USERS = set(settings.telegram_allowed_users)

storage = Storage()


# ------------------ CORE LOGIC ------------------

def confirm_payment_internal(code: str):
    meta_path = storage.metadata_path(code)

    print("DEBUG PATH:", meta_path)   # 👈 AGGIUNGI QUESTO

    if not meta_path.exists():
        raise Exception("Codice non trovato")

    metadata = storage.load_metadata(code)

    if metadata.get("status") == "paid" and metadata.get("redeem_token"):
        return metadata["redeem_token"]

    token = generate_redeem_token()

    metadata["redeem_token"] = token
    metadata["status"] = "paid"

    storage.save_metadata(code, metadata)

    logger.info("Pagamento manuale confermato per %s", code)

    return token


# ------------------ HANDLERS ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 LeoBrick Bot\n\n"
        "Invia un codice LEO-XXXX per generare il token RDM."
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id

    if user_id not in ALLOWED_USERS:
        return

    text = update.message.text.strip().upper()

    if not text.startswith("LEO-"):
        await update.message.reply_text("❌ Inserisci un codice valido (LEO-XXXX)")
        return

    logger.info("User %s → %s", user_id, text)

    msg = await update.message.reply_text("⏳ Genero token...")

    try:
        token = confirm_payment_internal(text)

        await msg.edit_text(
            f"✅ TOKEN GENERATO\n\n"
            f"Codice: {text}\n"
            f"RDM:\n{token}"
        )

    except Exception as e:
        await msg.edit_text(f"❌ Errore: {str(e)}")


# ------------------ START BOT (ASYNC SAFE) ------------------

async def start_bot_async():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle))

    logger.info("🤖 Bot Telegram avviato")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()