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
