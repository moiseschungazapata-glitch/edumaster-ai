"""Read-only post-deploy smoke test. Never prints or stores an access token."""
import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def endpoint(value: str, *, insecure_local: bool = False) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" and not (insecure_local and parsed.scheme == "http" and
                                            parsed.hostname in {"localhost", "127.0.0.1"}):
        raise ValueError("Usa HTTPS (HTTP solo para localhost con --local)")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Indica únicamente el origen, sin ruta, usuario ni parámetros")
    return value.rstrip("/")


def request(url: str, token: str | None = None) -> tuple[int, dict | None]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with urlopen(Request(url, headers=headers), timeout=10) as response:
            status, body = response.status, response.read(65536)
    except HTTPError as error:
        status, body = error.code, error.read(65536)
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        payload = None
    return status, payload


def run(api: str, web: str, token: str | None) -> None:
    # A recent rollout may need a few seconds for its database connection.
    for attempt in range(3):
        try:
            status, payload = request(f"{api}/health/ready")
        except (URLError, TimeoutError):
            status, payload = 0, None
        if status == 200 and payload == {"status": "ready"}:
            break
        if attempt < 2:
            time.sleep(2)
    else:
        raise RuntimeError("API no preparada: /health/ready")
    print("API ready: OK")

    status, _ = request(web)
    if status != 200:
        raise RuntimeError(f"Web no disponible: HTTP {status}")
    print("Web: OK")

    status, _ = request(f"{api}/api/v1/me")
    if status != 401:
        raise RuntimeError(f"Protección de /api/v1/me inesperada: HTTP {status}")
    print("Acceso sin sesión: 401 OK")

    if token:
        status, profile = request(f"{api}/api/v1/me", token)
        if status != 200 or not isinstance(profile, dict) or not profile.get("id"):
            raise RuntimeError(f"Sesión autenticada no disponible: HTTP {status}")
        print("Sesión autenticada: OK")
        status, model = request(f"{api}/api/v1/guidance/model/status", token)
        if status != 200 or not isinstance(model, dict) or model.get("prediction_enabled") is not False:
            raise RuntimeError("Estado del modelo no coincide con la versión demo prevista")
        print("Modelo demo sin inferencia: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba de humo de despliegue EduMaster")
    parser.add_argument("--api", required=True, help="Origen HTTPS de la API")
    parser.add_argument("--web", required=True, help="Origen HTTPS del frontend")
    parser.add_argument("--token-env", help="Nombre de variable de entorno con token de prueba opcional")
    parser.add_argument("--local", action="store_true", help="Permitir HTTP exclusivamente para localhost")
    args = parser.parse_args()
    try:
        api = endpoint(args.api, insecure_local=args.local)
        web = endpoint(args.web, insecure_local=args.local)
        token = os.environ.get(args.token_env) if args.token_env else None
        if args.token_env and not token:
            raise ValueError("Variable de token vacía")
        run(api, web, token)
    except (ValueError, RuntimeError, URLError, TimeoutError) as exc:
        print(f"FALLO: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
