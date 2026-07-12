from cryptography.fernet import Fernet
import os

KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", ".secret_key")


def _get_or_create_key() -> bytes:
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_PATH, "wb") as f:
        f.write(key)
    return key


_fernet = Fernet(_get_or_create_key())


def encrypt_token(token: str) -> str:
    return _fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()
