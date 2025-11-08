import logging

from mysql.connector import Error as MySQLError

from app.database import get_db, get_cursor

logger = logging.getLogger(__name__)


def init_db_command() -> None:
    cursor = get_cursor()
    log_prefix = "[DB:Schema:MySQL]"
    logger.info(f"{log_prefix} Checking/Initializing 'users' table schema...")
    try:
        cursor.execute("SHOW TABLES LIKE 'roles'")
        if not cursor.fetchone():
            logger.error(f"{log_prefix} Cannot initialize 'users' table: 'roles' table does not exist yet.")
            raise RuntimeError("Roles table must exist before users table can be initialized.")
        cursor.fetchall()

        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INT PRIMARY KEY AUTO_INCREMENT,
                username VARCHAR(80) UNIQUE NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(255),
                role_id INT,
                created_at DATETIME NOT NULL,
                api_keys_encrypted TEXT,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                oauth_provider VARCHAR(50),
                oauth_provider_id VARCHAR(255),
                default_content_language VARCHAR(10),
                default_transcription_model VARCHAR(50),
                enable_auto_title_generation BOOLEAN NOT NULL DEFAULT FALSE,
                FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE SET NULL,
                UNIQUE KEY uk_oauth (oauth_provider, oauth_provider_id),
                INDEX idx_username (username),
                INDEX idx_email (email),
                INDEX idx_oauth (oauth_provider, oauth_provider_id),
                INDEX idx_user_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            '''
        )
        logger.debug(f"{log_prefix} CREATE TABLE IF NOT EXISTS users executed.")

        cursor.execute("SHOW COLUMNS FROM users LIKE 'last_name'")
        last_name_exists = cursor.fetchone()
        cursor.fetchall()
        if not last_name_exists:
            logger.info(f"{log_prefix} Adding 'last_name' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN last_name VARCHAR(100) AFTER first_name")

        cursor.execute("SHOW COLUMNS FROM users LIKE 'oauth_provider'")
        oauth_provider_exists = cursor.fetchone()
        cursor.fetchall()
        if not oauth_provider_exists:
            logger.info(f"{log_prefix} Adding 'oauth_provider' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN oauth_provider VARCHAR(50) AFTER last_name")

        cursor.execute("SHOW COLUMNS FROM users LIKE 'oauth_provider_id'")
        oauth_provider_id_exists = cursor.fetchone()
        cursor.fetchall()
        if not oauth_provider_id_exists:
            logger.info(f"{log_prefix} Adding 'oauth_provider_id' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN oauth_provider_id VARCHAR(255) AFTER oauth_provider")

        cursor.execute("SHOW COLUMNS FROM users LIKE 'default_content_language'")
        default_lang_exists = cursor.fetchone()
        cursor.fetchall()
        if not default_lang_exists:
            logger.info(f"{log_prefix} Adding 'default_content_language' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN default_content_language VARCHAR(10) AFTER oauth_provider_id")

        cursor.execute("SHOW COLUMNS FROM users LIKE 'default_transcription_model'")
        default_model_exists = cursor.fetchone()
        cursor.fetchall()
        if not default_model_exists:
            logger.info(f"{log_prefix} Adding 'default_transcription_model' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN default_transcription_model VARCHAR(50) AFTER default_content_language")

        cursor.execute("SHOW COLUMNS FROM users LIKE 'enable_auto_title_generation'")
        auto_title_exists = cursor.fetchone()
        cursor.fetchall()
        if not auto_title_exists:
            logger.info(f"{log_prefix} Adding 'enable_auto_title_generation' column (BOOLEAN) to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN enable_auto_title_generation BOOLEAN NOT NULL DEFAULT FALSE AFTER default_transcription_model")

        cursor.execute("SHOW COLUMNS FROM users LIKE 'language'")
        language_col_exists = cursor.fetchone()
        cursor.fetchall()
        if not language_col_exists:
            logger.info(f"{log_prefix} Adding 'language' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN language VARCHAR(10) DEFAULT NULL AFTER default_transcription_model")

        cursor.execute("SHOW INDEX FROM users WHERE Key_name = 'uk_oauth'")
        uk_oauth_exists = cursor.fetchone()
        cursor.fetchall()
        if not uk_oauth_exists:
            logger.info(f"{log_prefix} Adding unique constraint 'uk_oauth' to 'users' table.")
            cursor.execute("SHOW INDEX FROM users WHERE Key_name = 'idx_oauth'")
            idx_oauth_exists = cursor.fetchone()
            cursor.fetchall()
            if not idx_oauth_exists:
                cursor.execute("ALTER TABLE users ADD INDEX idx_oauth (oauth_provider, oauth_provider_id)")
            cursor.execute("ALTER TABLE users ADD CONSTRAINT uk_oauth UNIQUE (oauth_provider, oauth_provider_id)")

        cursor.execute("SHOW INDEX FROM users WHERE Key_name = 'idx_user_created_at'")
        idx_created_at_exists = cursor.fetchone()
        cursor.fetchall()
        if not idx_created_at_exists:
            logger.info(f"{log_prefix} Adding index 'idx_user_created_at' to 'users' table.")
            cursor.execute("ALTER TABLE users ADD INDEX idx_user_created_at (created_at)")

        get_db().commit()
        logger.info(f"{log_prefix} 'users' table schema verified/initialized successfully.")
    except MySQLError as err:
        logger.error(f"{log_prefix} MySQL error during 'users' table initialization: {err}", exc_info=True)
        get_db().rollback()
        raise
    except RuntimeError as e:
        logger.error(f"{log_prefix} Initialization dependency error: {e}")
        get_db().rollback()
        raise
    finally:
        pass
