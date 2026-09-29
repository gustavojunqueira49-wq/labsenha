"""Hash de senhas (PBKDF2-SHA256, apenas biblioteca padrão) e tokens de sessão."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ITER = 260_000
_WEAK = {
    "12345678", "123456789", "1234567890", "password", "senha123", "admin123", "administrador",
    "qwerty123", "abc12345", "11111111", "00000000", "senha1234", "hospital123", "laboratorio",
}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def validate_password_strength(password: str, username: str = "") -> str | None:
    """Retorna mensagem de erro ou None se a senha for aceitável."""
    if len(password) < 8:
        return "A senha deve ter pelo menos 8 caracteres."
    if password.lower() in _WEAK or (username and password.lower() == username.lower()):
        return "Senha muito comum ou igual ao usuário."
    if password.isdigit() or password.isalpha():
        return "Use letras e números na senha."
    return None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def random_password(length: int = 12) -> str:
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if validate_password_strength(pw) is None:
            return pw
