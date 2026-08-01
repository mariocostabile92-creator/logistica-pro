import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = PROJECT_DIR / "frontend"

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "application/csv",
    "application/octet-stream",
}

DEFAULT_PREVIEW_ROWS = 10
RESERVE_VEHICLE_THRESHOLD = 1
PRODUCTION_ENVIRONMENTS = {"production", "prod"}


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _as_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _url_origin(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("BASE_URL e API_URL devono essere URL HTTP(S) validi.")
    return f"{parsed.scheme}://{parsed.netloc}"


@dataclass(frozen=True)
class Settings:
    environment: str
    debug: bool
    secret_key: str | None
    base_url: str
    api_url: str
    api_origin: str
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    database_url: str | None
    database_path: Path
    log_level: str
    max_upload_size_bytes: int
    runtime_storage_root: Path
    require_persistent_storage: bool

    @property
    def production(self) -> bool:
        return self.environment in PRODUCTION_ENVIRONMENTS

    @property
    def database_backend(self) -> str:
        if self.database_url and self.database_url.startswith(
            ("postgres://", "postgresql://", "postgresql+psycopg://")
        ):
            return "postgresql"
        return "sqlite"


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    values = os.environ if environ is None else environ
    environment = values.get("APP_ENV", "development").strip().casefold()
    valid_environments = {"development", "test"} | PRODUCTION_ENVIRONMENTS
    if environment not in valid_environments:
        raise ValueError("APP_ENV deve essere development, test o production.")

    production = environment in PRODUCTION_ENVIRONMENTS
    debug = _as_bool(values.get("DEBUG"), default=False)
    base_url = values.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    api_url = values.get("API_URL", base_url).rstrip("/")
    base_origin = _url_origin(base_url)
    api_origin = _url_origin(api_url)

    configured_origins = _as_csv(values.get("CORS_ORIGINS"))
    cors_origins = configured_origins or (
        (base_origin,)
        if production
        else (
            base_origin,
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        )
    )

    configured_hosts = _as_csv(values.get("TRUSTED_HOSTS"))
    trusted_hosts = configured_hosts or ("*",)

    database_url = values.get("DATABASE_URL", "").strip() or None
    valid_database_prefixes = (
        "postgres://",
        "postgresql://",
        "postgresql+psycopg://",
        "sqlite://",
    )
    if database_url and not database_url.startswith(valid_database_prefixes):
        raise ValueError("DATABASE_URL deve usare PostgreSQL o SQLite.")
    database_path = Path(
        values.get(
            "OPERATIONS_DB_PATH",
            str(DATA_DIR / "operations.sqlite3"),
        )
    )
    try:
        max_upload_mb = int(values.get("MAX_UPLOAD_SIZE_MB", "8"))
    except ValueError as exc:
        raise ValueError("MAX_UPLOAD_SIZE_MB deve essere un intero.") from exc
    if max_upload_mb < 1 or max_upload_mb > 100:
        raise ValueError("MAX_UPLOAD_SIZE_MB deve essere compreso tra 1 e 100.")

    secret_key = values.get("SECRET_KEY", "").strip() or None
    if production:
        if debug:
            raise ValueError("DEBUG deve essere false in produzione.")
        if not values.get("BASE_URL", "").strip():
            raise ValueError("BASE_URL e obbligatoria in produzione.")
        if not secret_key or len(secret_key) < 32:
            raise ValueError(
                "SECRET_KEY deve contenere almeno 32 caratteri in produzione."
            )
        if not database_url:
            raise ValueError("DATABASE_URL e obbligatoria in produzione.")
        if not database_url.startswith(
            ("postgres://", "postgresql://", "postgresql+psycopg://")
        ):
            raise ValueError("DATABASE_URL deve usare PostgreSQL in produzione.")
        if "*" in cors_origins:
            raise ValueError("CORS_ORIGINS non puo contenere * in produzione.")

    return Settings(
        environment=environment,
        debug=debug,
        secret_key=secret_key,
        base_url=base_url,
        api_url=api_url,
        api_origin=api_origin,
        cors_origins=cors_origins,
        trusted_hosts=trusted_hosts,
        database_url=database_url,
        database_path=database_path,
        log_level=values.get("LOG_LEVEL", "INFO").strip().upper(),
        max_upload_size_bytes=max_upload_mb * 1024 * 1024,
        runtime_storage_root=Path(
            values.get("RUNTIME_STORAGE_ROOT", str(DATA_DIR))
        ).expanduser().resolve(),
        require_persistent_storage=_as_bool(
            values.get("REQUIRE_PERSISTENT_STORAGE"), default=False
        ),
    )


SETTINGS = load_settings()
DATABASE_PATH = SETTINGS.database_path
MAX_UPLOAD_SIZE_BYTES = SETTINGS.max_upload_size_bytes


def ensure_data_dir() -> None:
    SETTINGS.database_path.parent.mkdir(parents=True, exist_ok=True)
