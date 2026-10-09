import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings

ALGORITHM = "HS256"


def _prehash(password: str) -> bytes:
    # bcrypt only reads 72 bytes; pre-hashing makes long passwords safe.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, s.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
