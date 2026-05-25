"""JWT authentication middleware / dependency."""
from __future__ import annotations

from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import get_db
from app.models.user import User
from app.services.jwt_service import decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
  request: Request,
  db: AsyncSession = Depends(get_db),
  credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
  required: bool = True,
) -> User | None:
  token: str | None = None

  # 1. Try Bearer header
  if credentials:
    token = credentials.credentials

  # 2. Fall back to cookie (web client)
  if not token:
    token = request.cookies.get("sc_session")

  if not token:
    if required:
      raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return None

  try:
    payload = decode_access_token(token)
  except JWTError:
    if required:
      raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return None

  user_id = payload.get("sub")
  result = await db.execute(select(User).where(User.id == user_id))
  user = result.scalar_one_or_none()
  if not user:
    if required:
      raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return None

  return user


# Convenience dependency (required=True)
CurrentUser = Depends(get_current_user)
