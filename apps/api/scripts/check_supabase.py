"""Read-only check of the Supabase project used by the web and API.

Run from apps/api: python -m scripts.check_supabase
No passwords, tokens, connection strings, or user email addresses are printed.
"""

import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

from app.core.config import database_url, supabase_url


EXPECTED_MIGRATION = "0005_audit"
REQUIRED_TABLES = {
    "institutions", "profiles", "courses", "lessons", "activities", "attempts",
    "enrollments", "lesson_progress", "learning_paths", "path_courses",
    "academic_events", "recommendations", "audit_records",
}


def check() -> bool:
    ok = True
    web_file = Path(__file__).resolve().parents[2] / "web" / ".env.local"
    web = dotenv_values(web_file) if web_file.is_file() else {}
    web_url = (web.get("VITE_SUPABASE_URL") or "").rstrip("/")
    web_key = web.get("VITE_SUPABASE_PUBLISHABLE_KEY") or ""
    api_url = supabase_url()
    api_project = urlparse(api_url).hostname
    web_project = urlparse(web_url).hostname
    same_project = bool(web_project and web_url == api_url)
    print(f"Web y API usan el mismo proyecto: {'OK' if same_project else 'FALLO'}")
    print(f"Clave pública de la web presente: {'OK' if web_key.startswith('sb_publishable_') else 'FALLO'}")
    ok = ok and same_project and web_key.startswith("sb_publishable_")

    # Supabase pooler usernames include the project ref. Direct connections use
    # db.<ref>.supabase.co instead. Both are checked when identifiable.
    db_url = database_url()
    db_parsed = urlparse(db_url)
    project_ref = api_project.split(".")[0] if api_project else ""
    db_identity = f"{db_parsed.username or ''} {db_parsed.hostname or ''}"
    db_matches = project_ref in db_identity if project_ref else False
    print(f"PostgreSQL identifica el mismo proyecto: {'OK' if db_matches else 'REVISAR'}")
    ok = ok and db_matches

    try:
        with urlopen(f"{api_url}/auth/v1/.well-known/jwks.json", timeout=8) as response:
            keys = json.load(response).get("keys", [])
        public_keys = any(key.get("kty") in {"RSA", "EC"} for key in keys)
        print(f"Claves públicas de autenticación disponibles: {'OK' if public_keys else 'FALLO'}")
        ok = ok and public_keys
    except Exception as exc:
        print(f"Autenticación no verificable ({type(exc).__name__}).")
        ok = False

    try:
        engine = create_engine(db_url, connect_args={"connect_timeout": 8})
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one_or_none()
            tables = dict(connection.execute(text("""
                SELECT c.relname, c.relrowsecurity
                FROM pg_class AS c
                WHERE c.relnamespace = 'public'::regnamespace
                  AND c.relkind IN ('r', 'p')
            """)).all())
            profile_count = connection.execute(text("SELECT count(*) FROM public.profiles")).scalar_one()
            unassigned = connection.execute(text("""
                SELECT count(*) FROM public.profiles WHERE institution_id IS NULL
            """)).scalar_one()
        engine.dispose()
        version_ok = version == EXPECTED_MIGRATION
        missing = REQUIRED_TABLES - tables.keys()
        rls_disabled = {name for name in REQUIRED_TABLES if name in tables and not tables[name]}
        print(f"Conexión PostgreSQL: OK")
        print(f"Migración {EXPECTED_MIGRATION}: {'OK' if version_ok else 'FALLO'} (actual: {version})")
        print(f"Tablas requeridas: {'OK' if not missing else 'FALLO'}")
        print(f"RLS en tablas requeridas: {'OK' if not rls_disabled else 'FALLO'}")
        print(f"Perfiles: {profile_count}; sin institución: {unassigned}")
        if missing:
            print("Tablas faltantes: " + ", ".join(sorted(missing)))
        if rls_disabled:
            print("Tablas sin RLS: " + ", ".join(sorted(rls_disabled)))
        ok = ok and version_ok and not missing and not rls_disabled
    except Exception as exc:
        print(f"PostgreSQL no verificable ({type(exc).__name__}).")
        ok = False

    print("Resultado: " + ("conexión y esquema verificados" if ok else "hay puntos pendientes"))
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if check() else 1)
