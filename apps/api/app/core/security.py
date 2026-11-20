import uuid
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.core.config import supabase_url
from app.core.db import get_db
from app.core.models import Profile

bearer = HTTPBearer(auto_error=False)


@lru_cache
def jwks() -> PyJWKClient:
    return PyJWKClient(f"{supabase_url()}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=300)


def get_identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar", headers={"WWW-Authenticate": "Bearer"})
    try:
        token = credentials.credentials
        key = jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["ES256", "RS256"],
            audience="authenticated", issuer=f"{supabase_url()}/auth/v1",
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        if claims.get("role") != "authenticated":
            raise ValueError("invalid auth role")
        uuid.UUID(claims["sub"])
        return claims
    except (jwt.PyJWTError, ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=401, detail="Sesión inválida o vencida", headers={"WWW-Authenticate": "Bearer"}) from exc


def get_current_profile(claims: dict = Depends(get_identity), db: Session = Depends(get_db)) -> Profile:
    profile = db.get(Profile, uuid.UUID(claims["sub"]))
    if profile is None:
        raise HTTPException(status_code=403, detail="Usuario sin perfil autorizado")
    return profile


def require_roles(*roles: str):
    def check(profile: Profile = Depends(get_current_profile)) -> Profile:
        if profile.role not in roles:
            raise HTTPException(status_code=403, detail="No tienes permisos para esta acción")
        return profile
    return check
