from app.utils import generate_redeem_token


def confirm_payment_internal(code: str, storage):
    # 🔴 CONTROLLO IMPORTANTE (ti mancava)
    meta_path = storage.metadata_path(code)

    if not meta_path.exists():
        raise Exception("Codice non trovato")

    metadata = storage.load_metadata(code)

    # ✅ già pagato → ritorna token
    if metadata.get("status") == "paid" and metadata.get("redeem_token"):
        return metadata["redeem_token"]

    # 🆕 genera token
    token = generate_redeem_token()

    metadata["redeem_token"] = token
    metadata["status"] = "paid"

    storage.save_metadata(code, metadata)

    return token