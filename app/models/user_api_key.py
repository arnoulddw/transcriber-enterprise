import logging
from typing import Dict, Optional

from mysql.connector import Error as MySQLError

from app.database import get_cursor, get_db


def init_db_command() -> None:
    """Initializes the 'user_api_keys' table schema."""
    cursor = get_cursor()
    log_prefix = "[DB:Schema:MySQL]"
    logging.info(f"{log_prefix} Checking/Initializing 'user_api_keys' table...")
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_api_keys (
                id INT PRIMARY KEY AUTO_INCREMENT,
                user_id INT NOT NULL,
                provider_code VARCHAR(80) NOT NULL,
                encrypted_key MEDIUMTEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_user_provider (user_id, provider_code),
                INDEX idx_user_api_key_provider (provider_code),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
        )
        # Ensure columns are correctly typed if table already exists
        for col_name, col_def in (
            ("created_at", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ):
            cursor.execute(f"SHOW COLUMNS FROM user_api_keys LIKE '{col_name}'")
            col_info = cursor.fetchone()
            cursor.fetchall()
            col_type = (col_info.get('Type') if isinstance(col_info, dict) else (col_info[1] if col_info else "")).lower()
            if col_info and 'timestamp' not in col_type:
                logging.info(f"{log_prefix} Converting '{col_name}' column on 'user_api_keys' table to TIMESTAMP.")
                cursor.execute(f"ALTER TABLE user_api_keys MODIFY COLUMN {col_name} {col_def}")

        cursor.execute("SHOW INDEX FROM user_api_keys WHERE Key_name = 'uq_user_provider'")
        unique_exists = cursor.fetchone()
        cursor.fetchall()
        if not unique_exists:
            logging.info(f"{log_prefix} Adding unique index uq_user_provider to 'user_api_keys'.")
            cursor.execute("ALTER TABLE user_api_keys ADD UNIQUE INDEX uq_user_provider (user_id, provider_code)")

        get_db().commit()
        logging.info(f"{log_prefix} 'user_api_keys' table schema verified/initialized.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error during 'user_api_keys' table initialization: {err}", exc_info=True)
        get_db().rollback()
        raise


def upsert_api_key(user_id: int, provider_code: str, encrypted_key: str) -> bool:
    provider = provider_code.lower()
    sql = """
        INSERT INTO user_api_keys (user_id, provider_code, encrypted_key)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE encrypted_key = VALUES(encrypted_key), updated_at = CURRENT_TIMESTAMP
    """
    cursor = get_cursor()
    try:
        cursor.execute(sql, (user_id, provider, encrypted_key))
        get_db().commit()
        return True
    except MySQLError as err:
        logging.error(f"[DB:UserApiKey] Error upserting API key for user {user_id}, provider {provider_code}: {err}", exc_info=True)
        get_db().rollback()
        return False


def get_api_key(user_id: int, provider_code: str) -> Optional[str]:
    provider = provider_code.lower()
    sql = "SELECT encrypted_key FROM user_api_keys WHERE user_id = %s AND provider_code = %s LIMIT 1"
    cursor = get_cursor()
    try:
        cursor.execute(sql, (user_id, provider))
        row = cursor.fetchone()
        return row['encrypted_key'] if row else None
    except MySQLError as err:
        logging.error(f"[DB:UserApiKey] Error retrieving API key for user {user_id}, provider {provider_code}: {err}", exc_info=True)
        return None


def delete_api_key(user_id: int, provider_code: str) -> bool:
    provider = provider_code.lower()
    sql = "DELETE FROM user_api_keys WHERE user_id = %s AND provider_code = %s"
    cursor = get_cursor()
    try:
        cursor.execute(sql, (user_id, provider))
        get_db().commit()
        return cursor.rowcount > 0
    except MySQLError as err:
        logging.error(f"[DB:UserApiKey] Error deleting API key for user {user_id}, provider {provider_code}: {err}", exc_info=True)
        get_db().rollback()
        return False


def delete_all_api_keys_for_user(user_id: int) -> None:
    cursor = get_cursor()
    try:
        cursor.execute("DELETE FROM user_api_keys WHERE user_id = %s", (user_id,))
        get_db().commit()
    except MySQLError as err:
        logging.error(f"[DB:UserApiKey] Error deleting all API keys for user {user_id}: {err}", exc_info=True)
        get_db().rollback()


def get_api_keys_by_user(user_id: int) -> Dict[str, str]:
    sql = "SELECT provider_code, encrypted_key FROM user_api_keys WHERE user_id = %s"
    cursor = get_cursor()
    keys: Dict[str, str] = {}
    try:
        cursor.execute(sql, (user_id,))
        rows = cursor.fetchall()
        for row in rows:
            keys[row['provider_code']] = row['encrypted_key']
    except MySQLError as err:
        logging.error(f"[DB:UserApiKey] Error fetching API keys for user {user_id}: {err}", exc_info=True)
    return keys
