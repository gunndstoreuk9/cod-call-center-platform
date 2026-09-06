import base64
import hashlib
import json
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.app_secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret_dict(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _fernet().encrypt(raw).decode("utf-8")


def decrypt_secret_dict(ciphertext: str | None) -> dict:
    if not ciphertext:
        return {}
    try:
        raw = _fernet().decrypt(ciphertext.encode("utf-8"))
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Decrypted integration secret is not an object")
        return value
    except InvalidToken as exc:
        raise ValueError("Integration secret decryption failed") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Integration secret payload is invalid") from exc
