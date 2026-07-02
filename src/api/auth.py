"""Clerk JWT authentication for FastAPI.

Verifies the Clerk session token from the Authorization header,
upserts the user into our DB, and returns the User ORM object.
"""

import httpx
import jwt
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.database.session import get_db_dependency as get_db
from src.database.models import User
from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _get_clerk_jwks() -> dict:
    """Fetch Clerk's JWKS (JSON Web Key Set) - cached for the process lifetime."""
    jwks_url = f"https://{settings.CLERK_FRONTEND_API}/.well-known/jwks.json"
    resp = httpx.get(jwks_url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _verify_clerk_token(token: str) -> dict:
    """Decode and verify a Clerk JWT. Returns the claims dict."""
    try:
        jwks = _get_clerk_jwks()
        public_keys = jwt.PyJWKClient(
            f"https://{settings.CLERK_FRONTEND_API}/.well-known/jwks.json"
        )
        signing_key = public_keys.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return claims
    except Exception as e:
        logger.warning(f"Clerk token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )


def _upsert_user(db: Session, clerk_id: str, email: Optional[str], full_name: Optional[str]) -> User:
    """Get or create a User row from Clerk identity."""
    user = db.query(User).filter(User.clerk_id == clerk_id).first()
    if user is None:
        try:
            user = User(clerk_id=clerk_id, email=email, full_name=full_name)
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"New user created: {clerk_id}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create user {clerk_id}: {e}")
            # Try again without email to avoid unique constraint on email
            user = db.query(User).filter(User.clerk_id == clerk_id).first()
            if not user:
                user = User(clerk_id=clerk_id, email=None, full_name=full_name)
                db.add(user)
                db.commit()
                db.refresh(user)
    elif email and user.email != email:
        try:
            user.email = email
            user.full_name = full_name
            db.commit()
        except Exception:
            db.rollback()
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency - returns the authenticated User or raises 401."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    claims = _verify_clerk_token(credentials.credentials)
    clerk_id = claims.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims.")

    email = claims.get("email") or (claims.get("email_addresses") or [{}])[0].get("email_address")
    full_name = claims.get("name") or f"{claims.get('first_name', '')} {claims.get('last_name', '')}".strip() or None

    return _upsert_user(db, clerk_id, email, full_name)


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None instead of 401 (for public endpoints)."""
    if not credentials:
        return None
    try:
        return get_current_user(credentials, db)
    except Exception:
        return None


def fetch_clerk_profile(clerk_id: str) -> dict:
    """Fetch email/name from Clerk's Backend API.

    Clerk's default session JWT does not include email/name claims (that
    requires a custom JWT template), so this is the reliable way to get a
    user's real profile info server-side.
    """
    try:
        resp = httpx.get(
            f"https://api.clerk.com/v1/users/{clerk_id}",
            headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        email_addresses = data.get("email_addresses", [])
        primary_email_id = data.get("primary_email_address_id")
        email = next(
            (e["email_address"] for e in email_addresses if e.get("id") == primary_email_id),
            email_addresses[0]["email_address"] if email_addresses else None,
        )
        name = f"{data.get('first_name', '') or ''} {data.get('last_name', '') or ''}".strip() or None
        return {"email": email, "name": name}
    except Exception as e:
        logger.warning(f"Failed to fetch Clerk profile for {clerk_id}: {e}")
        return {"email": None, "name": None}
