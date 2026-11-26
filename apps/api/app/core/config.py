import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def supabase_url() -> str:
    value = os.getenv("SUPABASE_URL", "").rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise RuntimeError("Configura SUPABASE_URL en apps/api/.env")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("SUPABASE_URL debe usar HTTPS fuera de desarrollo local")
    return value


def database_url() -> str:
    value = os.getenv("DATABASE_URL", "")
    if not value.startswith("postgresql+psycopg://"):
        raise RuntimeError("Configura DATABASE_URL con postgresql+psycopg://")
    return value


def allowed_origins() -> list[str]:
    return [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]


def validate_production_settings() -> None:
    """Reject missing or development settings before exposing a production API."""
    if os.getenv("APP_ENV", "development") != "production":
        return
    from urllib.parse import parse_qs

    url = supabase_url()
    parsed_db = urlparse(database_url())
    origins = allowed_origins()
    if not url.startswith("https://"):
        raise RuntimeError("SUPABASE_URL debe usar HTTPS en producción")
    if not parsed_db.hostname or not parsed_db.username or not parsed_db.password:
        raise RuntimeError("DATABASE_URL debe incluir host y credenciales en producción")
    if parse_qs(parsed_db.query).get("sslmode") != ["require"]:
        raise RuntimeError("DATABASE_URL debe usar sslmode=require en producción")
    if not os.getenv("CORS_ORIGINS") or not origins or any(
        not origin.startswith("https://") or "*" in origin or urlparse(origin).path not in {"", "/"}
        or not urlparse(origin).hostname or urlparse(origin).hostname in {"localhost", "127.0.0.1"}
        for origin in origins
    ):
        raise RuntimeError("CORS_ORIGINS debe incluir solo orígenes HTTPS públicos en producción")
