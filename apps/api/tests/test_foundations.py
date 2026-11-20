import uuid
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.core.models import Base, Profile
from app.core.security import get_identity
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
user_id = uuid.uuid4()
with Session(engine) as db:
    db.add(Profile(id=user_id, email="estudiante@example.com", role="student"))
    db.commit()


def test_public_health_and_private_routes():
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/api/v1/me").status_code == 401
        assert client.get("/api/v1/admin/ping").status_code == 401


def test_role_is_loaded_from_database_not_from_token():
    def test_db():
        with Session(engine) as db:
            yield db

    # An untrusted role in the token never determines the API permissions.
    app.dependency_overrides[get_identity] = lambda: {"sub": str(user_id), "role": "superadmin"}
    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            me = client.get("/api/v1/me")
            assert me.status_code == 200 and me.json()["role"] == "student"
            assert client.get("/api/v1/admin/ping").status_code == 403
            with Session(engine) as db:
                db.get(Profile, user_id).role = "admin"
                db.commit()
            assert client.get("/api/v1/admin/ping").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_invalid_signature_and_issuer_are_rejected(monkeypatch):
    from app.core import security

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(security, "jwks", lambda: SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=public)))
    claims = {"sub": str(user_id), "role": "authenticated", "aud": "authenticated", "iss": "https://example.supabase.co/auth/v1", "iat": 1, "exp": 4102444800}
    good = jwt.encode(claims, private, algorithm="RS256")
    bad_issuer = jwt.encode({**claims, "iss": "https://another.supabase.co/auth/v1"}, private, algorithm="RS256")
    bad_signature = jwt.encode(claims, rsa.generate_private_key(public_exponent=65537, key_size=2048), algorithm="RS256")
    def test_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {good}"}).status_code == 200
            assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {bad_issuer}"}).status_code == 401
            assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {bad_signature}"}).status_code == 401
    finally:
        app.dependency_overrides.clear()
