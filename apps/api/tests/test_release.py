import pytest
from sqlalchemy.pool import NullPool

from app.core.config import allowed_origins, validate_production_settings
from scripts.smoke_release import endpoint


def test_production_requires_https_tls_and_explicit_cors(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db.example.com:5432/postgres?sslmode=require")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    validate_production_settings()

    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        validate_production_settings()

    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db.example.com/postgres")
    with pytest.raises(RuntimeError, match="sslmode"):
        validate_production_settings()


def test_release_smoke_rejects_insecure_or_credential_urls():
    assert endpoint("https://api.example.com/") == "https://api.example.com"
    with pytest.raises(ValueError):
        endpoint("http://api.example.com")
    with pytest.raises(ValueError):
        endpoint("https://user:password@api.example.com")
    assert endpoint("http://127.0.0.1:8000", insecure_local=True) == "http://127.0.0.1:8000"


def test_vercel_uses_short_lived_database_connections(monkeypatch):
    from app.core import db

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(db, "database_url", lambda: "postgresql+psycopg://user:password@localhost/postgres")
    create_engine = db.create_engine
    seen = {}

    def observe(url, **options):
        seen.update(options)
        return create_engine(url, **options)

    monkeypatch.setattr(db, "create_engine", observe)
    db.engine.cache_clear()
    try:
        instance = db.engine()
        assert isinstance(instance.pool, NullPool)
        assert seen["connect_args"]["prepare_threshold"] is None
        instance.dispose()
    finally:
        db.engine.cache_clear()


def test_single_project_disables_cross_origin_requests(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SAME_ORIGIN_ONLY", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db.example.com/postgres?sslmode=require")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    validate_production_settings()
    assert allowed_origins() == []
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        validate_production_settings()
