# app/models/transcription_catalog.py
# Centralized catalog for transcription models and supported languages.
# Provides a single source of truth backed by MySQL tables.

import logging
from typing import Dict, List, Optional, Tuple

from flask import current_app
from mysql.connector import Error as MySQLError

from app.database import get_db, get_cursor

logger = logging.getLogger(__name__)

# Table names kept in constants to avoid typos.
MODELS_TABLE = "transcription_models_catalog"
LANGUAGES_TABLE = "transcription_languages_catalog"

# Default metadata for known providers. Extend this list when new providers are introduced.
_DEFAULT_MODEL_METADATA: Dict[str, Dict[str, Optional[str]]] = {
    "gpt-4o-transcribe": {
        "display_name": "OpenAI GPT-4o Transcribe",
        "permission_key": "use_api_openai_gpt_4o_transcribe",
        "required_api_key": "openai",
        "sort_order": 20,
    },
    "gpt-4o-transcribe-diarize": {
        "display_name": "OpenAI GPT-4o Diarize",
        "permission_key": "use_api_openai_gpt_4o_transcribe_diarize",
        "required_api_key": "openai",
        "sort_order": 30,
    },
    "whisper": {
        "display_name": "OpenAI Whisper",
        "permission_key": "use_api_openai_whisper",
        "required_api_key": "openai",
        "sort_order": 10,
    },
    "assemblyai": {
        "display_name": "AssemblyAI",
        "permission_key": "use_api_assemblyai",
        "required_api_key": "assemblyai",
        "sort_order": 40,
    },
}


def init_db_command() -> None:
    """
    Ensures the catalog tables exist and are seeded with defaults derived from config.
    Safe to call multiple times.
    """
    cursor = get_cursor()
    log_prefix = "[DB:Catalog]"
    logger.info(f"{log_prefix} Ensuring transcription catalog tables exist.")

    try:
        _ensure_models_table(cursor)
        _ensure_languages_table(cursor)
        get_db().commit()
    except MySQLError as err:
        get_db().rollback()
        logger.error(f"{log_prefix} Failed to initialize catalog tables: {err}", exc_info=True)
        raise

    # Seed defaults after the tables are in place.
    try:
        seed_from_config()
    except Exception as seed_err:
        logger.error(f"{log_prefix} Failed to seed catalog tables: {seed_err}", exc_info=True)
        raise


def seed_from_config() -> None:
    """
    Seeds models and languages based on the current Flask config.
    Existing rows are upserted to keep display names and defaults in sync.
    """
    _seed_models_from_config()
    _seed_languages_from_config()


def get_active_models() -> List[Dict[str, Optional[str]]]:
    """
    Returns active transcription models sorted by configured order.
    """
    if not _table_has_rows(MODELS_TABLE):
        seed_from_config()

    cursor = get_cursor()
    sql = f"""
        SELECT code, display_name, permission_key, required_api_key, is_default
        FROM {MODELS_TABLE}
        WHERE is_active = TRUE
        ORDER BY sort_order ASC, display_name ASC
    """
    cursor.execute(sql)
    rows = cursor.fetchall() or []
    models: List[Dict[str, Optional[str]]] = []
    for row in rows:
        models.append(
            {
                "code": row["code"],
                "display_name": row["display_name"],
                "permission_key": row.get("permission_key"),
                "required_api_key": row.get("required_api_key"),
                "is_default": bool(row.get("is_default", False)),
            }
        )
    return models


def get_model_by_code(code: str) -> Optional[Dict[str, Optional[str]]]:
    if not code:
        return None
    cursor = get_cursor()
    sql = f"""
        SELECT code, display_name, permission_key, required_api_key, is_default, is_active
        FROM {MODELS_TABLE}
        WHERE code = %s
        LIMIT 1
    """
    cursor.execute(sql, (code,))
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "code": row["code"],
        "display_name": row["display_name"],
        "permission_key": row.get("permission_key"),
        "required_api_key": row.get("required_api_key"),
        "is_default": bool(row.get("is_default", False)),
        "is_active": bool(row.get("is_active", False)),
    }


def get_default_model_code() -> Optional[str]:
    models = get_active_models()
    for model in models:
        if model.get("is_default"):
            return model["code"]
    # Fallback to the first active model if no explicit default is set.
    if models:
        return models[0]["code"]
    return None


def get_active_languages() -> List[Dict[str, Optional[str]]]:
    if not _table_has_rows(LANGUAGES_TABLE):
        seed_from_config()

    cursor = get_cursor()
    sql = f"""
        SELECT code, display_name, is_default
        FROM {LANGUAGES_TABLE}
        WHERE is_active = TRUE
        ORDER BY sort_order ASC, display_name ASC
    """
    cursor.execute(sql)
    rows = cursor.fetchall() or []
    languages: List[Dict[str, Optional[str]]] = []
    for row in rows:
        languages.append(
            {
                "code": row["code"],
                "display_name": row["display_name"],
                "is_default": bool(row.get("is_default", False)),
            }
        )
    return languages


def get_language_map() -> Dict[str, str]:
    """
    Returns a dict mapping language code to display name for active languages.
    """
    return {lang["code"]: lang["display_name"] for lang in get_active_languages()}


def get_default_language_code() -> Optional[str]:
    languages = get_active_languages()
    for lang in languages:
        if lang.get("is_default"):
            return lang["code"]
    if languages:
        return languages[0]["code"]
    return None


# ----- Internal Helpers -----

def _ensure_models_table(cursor) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MODELS_TABLE} (
            id INT PRIMARY KEY AUTO_INCREMENT,
            code VARCHAR(80) NOT NULL UNIQUE,
            display_name VARCHAR(120) NOT NULL,
            permission_key VARCHAR(120) DEFAULT NULL,
            required_api_key VARCHAR(80) DEFAULT NULL,
            sort_order INT NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
    )


def _ensure_languages_table(cursor) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LANGUAGES_TABLE} (
            id INT PRIMARY KEY AUTO_INCREMENT,
            code VARCHAR(20) NOT NULL UNIQUE,
            display_name VARCHAR(120) NOT NULL,
            sort_order INT NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
    )


def _seed_models_from_config() -> None:
    config = current_app.config
    codes: List[str] = config.get("TRANSCRIPTION_PROVIDERS", [])
    default_code: Optional[str] = config.get("DEFAULT_TRANSCRIPTION_PROVIDER")
    name_map: Dict[str, str] = config.get("API_PROVIDER_NAME_MAP", {})

    if not codes:
        logger.warning("[Catalog] TRANSCRIPTION_PROVIDERS config is empty. No models to seed.")
        return

    for index, code in enumerate(codes):
        metadata = _DEFAULT_MODEL_METADATA.get(code, {})
        display_name = name_map.get(code, metadata.get("display_name") or code)
        permission_key = metadata.get("permission_key")
        required_api_key = metadata.get("required_api_key")
        sort_order = metadata.get("sort_order", (index + 1) * 10)
        _upsert_model(
            code=code,
            display_name=display_name,
            permission_key=permission_key,
            required_api_key=required_api_key,
            sort_order=sort_order,
            is_active=True,
            is_default=(code == default_code),
        )

    if default_code:
        _set_default_model(default_code)


def _seed_languages_from_config() -> None:
    config = current_app.config
    codes: List[str] = config.get("SUPPORTED_LANGUAGE_CODES", [])
    names_map: Dict[str, str] = config.get("SUPPORTED_LANGUAGE_NAMES", {})
    default_code: Optional[str] = config.get("DEFAULT_LANGUAGE")

    ordered_codes: List[str] = []

    def _append_code(code: Optional[str]) -> None:
        if code and code not in ordered_codes:
            ordered_codes.append(code)

    if 'auto' in names_map:
        _append_code('auto')

    for code in codes:
        _append_code(code)

    for code in names_map.keys():
        if code != 'auto':
            _append_code(code)

    _append_code(default_code)

    if not ordered_codes:
        logger.warning("[Catalog] No languages available to seed.")
        return

    for index, code in enumerate(ordered_codes):
        display_name = _coerce_string(names_map.get(code, code))
        sort_order = (index + 1) * 10
        _upsert_language(
            code=code,
            display_name=display_name,
            sort_order=sort_order,
            is_active=True,
            is_default=(code == default_code),
        )

    if default_code:
        _set_default_language(default_code)


def _table_has_rows(table_name: str) -> bool:
    cursor = get_cursor()
    try:
        cursor.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
    except MySQLError as err:
        if getattr(err, "errno", None) == 1146:  # Table doesn't exist
            logger.info(f"[Catalog] Table '{table_name}' missing. Re-initializing catalog tables.")
            init_db_command()
            cursor = get_cursor()
            cursor.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
        else:
            raise
    return cursor.fetchone() is not None


def _upsert_model(
    *,
    code: str,
    display_name: str,
    permission_key: Optional[str],
    required_api_key: Optional[str],
    sort_order: int,
    is_active: bool,
    is_default: bool,
) -> None:
    sql = f"""
        INSERT INTO {MODELS_TABLE} (code, display_name, permission_key, required_api_key, sort_order, is_active, is_default)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            display_name = VALUES(display_name),
            permission_key = VALUES(permission_key),
            required_api_key = VALUES(required_api_key),
            sort_order = VALUES(sort_order),
            is_active = VALUES(is_active),
            is_default = VALUES(is_default)
    """
    cursor = get_cursor()
    cursor.execute(
        sql,
        (
            code,
            _coerce_string(display_name),
            permission_key,
            required_api_key,
            sort_order,
            int(bool(is_active)),
            int(bool(is_default)),
        ),
    )
    get_db().commit()


def _set_default_model(default_code: str) -> None:
    cursor = get_cursor()
    cursor.execute(
        f"UPDATE {MODELS_TABLE} SET is_default = CASE WHEN code = %s THEN TRUE ELSE FALSE END",
        (default_code,),
    )
    get_db().commit()


def _upsert_language(
    *,
    code: str,
    display_name: str,
    sort_order: int,
    is_active: bool,
    is_default: bool,
) -> None:
    sql = f"""
        INSERT INTO {LANGUAGES_TABLE} (code, display_name, sort_order, is_active, is_default)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            display_name = VALUES(display_name),
            sort_order = VALUES(sort_order),
            is_active = VALUES(is_active),
            is_default = VALUES(is_default)
    """
    cursor = get_cursor()
    cursor.execute(
        sql,
        (
            code,
            _coerce_string(display_name),
            sort_order,
            int(bool(is_active)),
            int(bool(is_default)),
        ),
    )
    get_db().commit()


def _set_default_language(default_code: str) -> None:
    cursor = get_cursor()
    cursor.execute(
        f"UPDATE {LANGUAGES_TABLE} SET is_default = CASE WHEN code = %s THEN TRUE ELSE FALSE END",
        (default_code,),
    )
    get_db().commit()
def _coerce_string(value: Optional[str]) -> Optional[str]:
    """
    Ensures SQL parameters receive plain Python strings (not LazyString instances).
    """
    if value is None:
        return None
    return str(value)
