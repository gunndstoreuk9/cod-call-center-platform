import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import SessionToken, User

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> tuple[str, SessionToken]:
    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    row = SessionToken(
        user_id=user.id,
        token_hash=_token_hash(token),
        expires_at=now + timedelta(hours=settings.session_hours),
        last_seen_at=now,
    )
    db.add(row)
    user.last_login_at = now
    db.commit()
    db.refresh(row)
    return token, row


def get_session_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    now = datetime.now(timezone.utc)
    row = (
        db.query(SessionToken)
        .filter(SessionToken.token_hash == _token_hash(token), SessionToken.expires_at > now)
        .first()
    )
    if not row:
        return None
    user = db.query(User).filter(User.id == row.user_id, User.is_active.is_(True)).first()
    if user:
        row.last_seen_at = now
        db.commit()
    return user


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    db.query(SessionToken).filter(SessionToken.token_hash == _token_hash(token)).delete()
    db.commit()
