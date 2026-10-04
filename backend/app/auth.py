"""Mock auth: JWT bearer tokens. Role isolation is enforced here (API level), not only in the UI."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import settings
from .db import get_db
from .errors import ApiError
from .models import User

_bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_TTL_HOURS)
    return jwt.encode({"sub": user.username, "role": user.role, "agent_id": user.agent_id, "exp": exp},
                      settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def user_public(u: User) -> dict:
    return {"username": u.username, "role": u.role, "agent_id": u.agent_id, "display_name": u.display_name}


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise ApiError(401, "unauthorized", "Authentication required")
    try:
        payload = jwt.decode(cred.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except jwt.PyJWTError:
        raise ApiError(401, "unauthorized", "Invalid or expired token")
    user = db.scalar(select(User).where(User.username == payload.get("sub")))
    if user is None:
        raise ApiError(401, "unauthorized", "Unknown user")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise ApiError(403, "forbidden", "Admin access required")
    return user


def authorize_agent(user: User, agent_id: str) -> str:
    """Agents may only touch their own agent_id; admins may touch any."""
    agent_id = agent_id.upper()
    if user.role == "agent" and user.agent_id != agent_id:
        raise ApiError(403, "forbidden", "You can only access your own data")
    return agent_id
