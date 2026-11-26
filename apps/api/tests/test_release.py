import pytest

from app.core.config import validate_production_settings
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
