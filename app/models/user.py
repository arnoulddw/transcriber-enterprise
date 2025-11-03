# app/models/user.py
# Defines the User model, its relationship with Roles, and core database interaction functions for MySQL.

import logging
logger = logging.getLogger(__name__)
import os
from flask import current_app
from flask_login import UserMixin
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

# Import MySQL specific error class
from mysql.connector import Error as MySQLError

# Import centralized DB functions (now MySQL based)
from app.database import get_db, get_cursor
from app.models import transcription_catalog as transcription_catalog_model

# Import Role model and related functions needed for user operations
try:
    from app.models.role import Role, get_role_by_id, get_role_by_name
except ImportError as e:
    logger.critical(f"[DB:Models:User] Failed to import Role model dependencies: {e}. This may cause runtime errors.")
    Role = None # type: ignore
    get_role_by_id = None # type: ignore
    get_role_by_name = None # type: ignore


# --- User Model Class ---
class User(UserMixin):
    id: int
    username: str
    email: str
    password_hash: Optional[str]
    role_id: Optional[int]
    created_at: str
    api_keys_encrypted: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    oauth_provider: Optional[str]
    oauth_provider_id: Optional[str]
    default_content_language: Optional[str]
    default_transcription_model: Optional[str]
    enable_auto_title_generation: bool
    language: Optional[str]
    _role: Optional['Role']
    def __init__(self, id: int, username: str, email: str, password_hash: Optional[str], role_id: Optional[int], created_at: str,
                 api_keys_encrypted: Optional[str] = None,
                 first_name: Optional[str] = None,
                 last_name: Optional[str] = None,
                 oauth_provider: Optional[str] = None,
                 oauth_provider_id: Optional[str] = None,
                 default_content_language: Optional[str] = None,
                 default_transcription_model: Optional[str] = None,
                 enable_auto_title_generation: bool = False,
                 language: Optional[str] = None
                 ):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.role_id = role_id
        self.created_at = created_at
        self.api_keys_encrypted = api_keys_encrypted
        self.first_name = first_name
        self.last_name = last_name
        self.oauth_provider = oauth_provider
        self.oauth_provider_id = oauth_provider_id
        self.default_content_language = default_content_language
        self.default_transcription_model = default_transcription_model
        self.enable_auto_title_generation = enable_auto_title_generation
        self.language = language
        self._role = None

    @property
    def role(self) -> Optional['Role']:
        try:
            logger.debug(f"[User:{self.id}] role property accessed. cached={self._role is not None}, role_id={self.role_id}")
        except Exception:
            pass
        if self._role is None and self.role_id is not None:
            from app.models.role import _map_row_to_role
            sql = 'SELECT * FROM roles WHERE id = %s'
            cursor = None
            try:
                cursor = get_cursor()
                cursor.execute(sql, (self.role_id,))
                row = cursor.fetchone()
                self._role = _map_row_to_role(row)
                if self._role:
                    logger.debug(f"[User:{self.id}] Loaded role snapshot from DB. role_id={self.role_id}, role_name={getattr(self._role, 'name', None)}")
                else:
                    logger.warning(f"[User:{self.id}] No role found for role_id={self.role_id}.")
            except MySQLError as err:
                logger.error(f"[User:{self.id}] Error fetching role (ID: {self.role_id}): {err}", exc_info=True)
                self._role = None
            finally:
                if cursor:
                    # The cursor is managed by the application context, so we don't close it here.
                    pass
        elif self.role_id is None:
             logger.warning(f"[User:{self.id}] User has no role_id assigned.")
        return self._role

    def has_permission(self, permission_name: str) -> bool:
        return self.role.has_permission(permission_name) if self.role else False

    def get_limit(self, limit_name: str) -> int:
        return self.role.get_limit(limit_name) if self.role else 0

    def get_total_minutes(self) -> float:
        """Calculates the total transcription minutes used by the user."""
        from app.models.user_utils import get_user_usage_stats
        stats = get_user_usage_stats(self.id)
        return stats.get('total_minutes', 0.0)

    def __repr__(self):
        role_info = f"Role:{self.role.name}" if self.role else f"RoleID:{self.role_id}"
        oauth_info = f", Provider:{self.oauth_provider}" if self.oauth_provider else ""
        name_info = f", Name: {self.first_name or ''} {self.last_name or ''}".strip() if self.first_name or self.last_name else ""
        return f'<User {self.username} (ID: {self.id}, Email: {self.email}{name_info}, {role_info}{oauth_info})>'

# --- Database Schema Initialization ---

def init_db_command() -> None:
    cursor = get_cursor()
    log_prefix = "[DB:Schema:MySQL]"
    logger.info(f"{log_prefix} Checking/Initializing 'users' table schema...")
    try:
        cursor.execute("SHOW TABLES LIKE 'roles'")
        if not cursor.fetchone():
            logger.error(f"{log_prefix} Cannot initialize 'users' table: 'roles' table does not exist yet.")
            raise RuntimeError("Roles table must exist before users table can be initialized.")
        cursor.fetchall() # Consume results if any

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
                INDEX idx_user_created_at (created_at) -- Index for signup analytics
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            '''
        )
        logger.debug(f"{log_prefix} CREATE TABLE IF NOT EXISTS users executed.")

        # --- Idempotent ALTER TABLE ---

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

        # --- NEW: Add 'language' column for UI preference ---
        cursor.execute("SHOW COLUMNS FROM users LIKE 'language'")
        language_col_exists = cursor.fetchone()
        cursor.fetchall()
        if not language_col_exists:
            logger.info(f"{log_prefix} Adding 'language' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN language VARCHAR(10) DEFAULT NULL AFTER default_transcription_model")
        # --- END NEW ---

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
        # --- End ALTER TABLE ---

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
        # The cursor is managed by the application context, so we don't close it here.
        pass

# --- User Data Access Functions (Core) ---

def _map_row_to_user(row: Dict[str, Any]) -> Optional[User]:
    if row:
        required_fields = ['id', 'username', 'email', 'created_at']
        if not all(field in row for field in required_fields):
             logger.error(f"[DB:User] Database row missing required fields for User object: {row}")
             return None
        user = User(
            id=row['id'], username=row['username'], email=row['email'],
            password_hash=row.get('password_hash'), role_id=row.get('role_id'),
            created_at=row['created_at'], api_keys_encrypted=row.get('api_keys_encrypted'),
            first_name=row.get('first_name'),
            last_name=row.get('last_name'),
            oauth_provider=row.get('oauth_provider'),
            oauth_provider_id=row.get('oauth_provider_id'),
            default_content_language=row.get('default_content_language'),
            default_transcription_model=row.get('default_transcription_model'),
            enable_auto_title_generation=bool(row.get('enable_auto_title_generation', False)),
            language=row.get('language')
        )
        # Do not pre-populate a partial Role object from a joined 'role_name' only.
        # Allow lazy-loading via user.role property to fetch the complete Role with permissions.
        return user
    return None

def _get_default_transcription_model_for_new_user(role: Role) -> Optional[str]:
    """
    Determines the default transcription model for a new user based on their role and system config.
    """
    if not role:
        return None

    try:
        catalog_models = transcription_catalog_model.get_active_models()
    except Exception as catalog_err:
        logger.error(f"[DB:User] Failed to load transcription model catalog: {catalog_err}", exc_info=True)
        catalog_models = []

    if not catalog_models:
        logger.warning(f"[DB:User] No active transcription models available while creating user with role '{role.name}'.")
        return current_app.config.get('DEFAULT_TRANSCRIPTION_PROVIDER')

    permitted_model_codes: List[str] = []
    default_model_code: Optional[str] = None

    for model in catalog_models:
        permission_key = model.get('permission_key')
        if not permission_key or getattr(role, permission_key, False):
            permitted_model_codes.append(model['code'])
            if model.get('is_default'):
                default_model_code = model['code']

    if not permitted_model_codes:
        logger.warning(f"[DB:User] New user with role '{role.name}' has no transcription providers permitted.")
        return None

    if default_model_code and default_model_code in permitted_model_codes:
        logger.debug(f"[DB:User] Setting default model for new user to catalog default: '{default_model_code}'")
        return default_model_code

    fallback_provider = permitted_model_codes[0]
    logger.debug(f"[DB:User] Catalog default not permitted for role '{role.name}'. Falling back to first available: '{fallback_provider}'")
    return fallback_provider

def add_user(username: str, email: str, password_hash: str, role_name: str = 'beta-tester', language: Optional[str] = None) -> Optional[User]:
    if get_role_by_name is None: return None
    logger.info(f"[DB:User] Adding user with role_name: {role_name}")
    role = get_role_by_name(role_name)
    if not role:
        logger.error(f"[DB:User] Cannot add user '{username}': Role '{role_name}' not found.")
        if role_name != 'beta-tester':
            logger.warning(f"[DB:User] Falling back to default role 'beta-tester' for user '{username}'.")
            role = get_role_by_name('beta-tester')
        if not role:
            logger.critical(f"[DB:User] Default role 'beta-tester' also not found. Cannot create user '{username}'.")
            return None
    role_id = role.id
    logger.info(f"[DB:User] Role ID to be inserted: {role_id}")

    # --- MODIFIED: Get default settings for new user ---
    default_model = _get_default_transcription_model_for_new_user(role)
    default_language = transcription_catalog_model.get_default_language_code() or current_app.config.get('DEFAULT_LANGUAGE', 'auto')
    # --- END MODIFIED ---

    default_auto_title_enabled = False
    if role:
        has_perm = role.has_permission('allow_auto_title_generation')
        logger.info(f"[DB:User] Role '{role.name}' allow_auto_title_generation permission: {getattr(role, 'allow_auto_title_generation', 'ATTR_MISSING')}, has_permission()={has_perm}")
        if has_perm:
            default_auto_title_enabled = True
    else:
        logger.warning(f"[DB:User] No role provided for default auto-title check")

    # --- MODIFIED: Add new columns to INSERT statement ---
    sql = '''
        INSERT INTO users (
            username, email, password_hash, role_id, created_at,
            enable_auto_title_generation, language,
            default_content_language, default_transcription_model
        )
        VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s, %s)
        '''
    # --- END MODIFIED ---
    cursor = get_cursor()
    try:
        # --- MODIFIED: Pass new default values to execute() ---
        cursor.execute(sql, (
            username, email, password_hash, role.id,
            default_auto_title_enabled, language,
            default_language, default_model
        ))
        # --- END MODIFIED ---
        user_id = cursor.lastrowid
        # --- MODIFIED: Update log message ---
        logger.info(f"[DB:User] Added new user '{username}' (Email: {email}) with ID {user_id}, role '{role_name}' (ID: {role_id}), AutoTitle: {default_auto_title_enabled}, Language: {language}, DefaultModel: {default_model}.")
        # --- END MODIFIED ---
        user = get_user_by_id(user_id)
        if user:
            user._role = get_role_by_name(role_name)
        return user
    except MySQLError as err:
        get_db().rollback()
        if err.errno == 1062:
            if 'users.username' in err.msg or 'idx_username' in err.msg:
                 logger.warning(f"[DB:User] Attempted to add user with duplicate username: {username}")
            elif 'users.email' in err.msg or 'idx_email' in err.msg:
                 logger.warning(f"[DB:User] Attempted to add user with duplicate email: {email}")
            else:
                 logger.warning(f"[DB:User] Duplicate entry error adding user '{username}'/'{email}': {err}")
        else:
            logger.error(f"[DB:User] Error adding user '{username}': {err}", exc_info=True)
        return None
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def add_oauth_user(email: str, first_name: Optional[str], last_name: Optional[str],
                   oauth_provider: str, oauth_provider_id: str,
                   role_name: str = 'beta-tester', language: Optional[str] = None) -> Optional[User]:
    if get_role_by_name is None: return None
    role = get_role_by_name(role_name)
    if not role:
        logger.error(f"[DB:User] Cannot add OAuth user '{email}': Role '{role_name}' not found.")
        if role_name != 'beta-tester':
            logger.warning(f"[DB:User] Falling back to default role 'beta-tester' for OAuth user '{email}'.")
            role = get_role_by_name('beta-tester')
        if not role:
            logger.critical(f"[DB:User] Default role 'beta-tester' also not found. Cannot create OAuth user '{email}'.")
            return None
    role_id = role.id

    # --- MODIFIED: Get default settings for new user ---
    default_model = _get_default_transcription_model_for_new_user(role)
    default_language = transcription_catalog_model.get_default_language_code() or current_app.config.get('DEFAULT_LANGUAGE', 'auto')
    # --- END MODIFIED ---

    default_auto_title_enabled = False
    if role and role.has_permission('allow_auto_title_generation'):
        default_auto_title_enabled = True

    username_base = email.split('@')[0].lower().replace('.', '').replace('+', '')
    username = username_base
    suffix = 1
    while get_user_by_username(username):
        username = f"{username_base}{suffix}"
        suffix += 1
        if suffix > 100:
             logger.error(f"[DB:User] Could not generate unique username for OAuth user '{email}' after {suffix-1} attempts.")
             return None

    # --- MODIFIED: Add new columns to INSERT statement ---
    sql = '''
        INSERT INTO users (
            username, email, password_hash, role_id, created_at,
            first_name, last_name, oauth_provider, oauth_provider_id,
            enable_auto_title_generation, language,
            default_content_language, default_transcription_model
        )
        VALUES (%s, %s, NULL, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
        '''
    # --- END MODIFIED ---
    cursor = get_cursor()
    try:
        # --- MODIFIED: Pass new default values to execute() ---
        cursor.execute(sql, (
            username, email, role_id,
            first_name, last_name, oauth_provider, oauth_provider_id,
            default_auto_title_enabled, language,
            default_language, default_model
        ))
        # --- END MODIFIED ---
        get_db().commit()
        user_id = cursor.lastrowid
        # --- MODIFIED: Update log message ---
        logger.info(f"[DB:User] Added new OAuth user '{username}' (Email: {email}, Provider: {oauth_provider}) with ID {user_id}, role '{role_name}' (ID: {role_id}), AutoTitle: {default_auto_title_enabled}, Language: {language}, DefaultModel: {default_model}.")
        # --- END MODIFIED ---
        return get_user_by_id(user_id)
    except MySQLError as err:
        get_db().rollback()
        if err.errno == 1062:
            if 'users.email' in err.msg or 'idx_email' in err.msg:
                 logger.warning(f"[DB:User] Attempted to add OAuth user with duplicate email: {email}")
            elif 'uk_oauth' in err.msg:
                 logger.warning(f"[DB:User] Attempted to add OAuth user with duplicate provider/id: {oauth_provider}/{oauth_provider_id}")
            else:
                 logger.warning(f"[DB:User] Duplicate entry error adding OAuth user '{email}': {err}")
        else:
            logger.error(f"[DB:User] Error adding OAuth user '{email}': {err}", exc_info=True)
        return None
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def get_user_by_username(username: str) -> Optional[User]:
    sql = 'SELECT u.*, r.name as role_name FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.username = %s'
    cursor = None
    user = None
    try:
        cursor = get_cursor()
        cursor.execute(sql, (username,))
        row = cursor.fetchone()
        user = _map_row_to_user(row)
    except MySQLError as err:
        logger.error(f"[DB:User] Error retrieving user by username '{username}': {err}", exc_info=True)
        user = None # Ensure user is None on error
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return user

def get_user_by_email(email: str) -> Optional[User]:
    sql = 'SELECT u.*, r.name as role_name FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.email = %s'
    cursor = None
    user = None
    try:
        cursor = get_cursor()
        cursor.execute(sql, (email,))
        row = cursor.fetchone()
        user = _map_row_to_user(row)
    except MySQLError as err:
        logger.error(f"[DB:User] Error retrieving user by email '{email}': {err}", exc_info=True)
        user = None # Ensure user is None on error
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return user

def get_user_by_id(user_id: int) -> Optional[User]:
    sql = 'SELECT u.*, r.name as role_name FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.id = %s'
    cursor = None
    user = None
    try:
        cursor = get_cursor()
        cursor.execute(sql, (user_id,))
        row = cursor.fetchone()
        if row:
            logger.info(f"[DB:User] get_user_by_id({user_id}) - DB row: username={row.get('username')}, role_id={row.get('role_id')}, role_name={row.get('role_name')}")
            user = _map_row_to_user(row)
            # Eagerly pin role snapshot to avoid drift during long-running operations/tests
            if user and user.role_id is not None:
                try:
                    role_snapshot = get_role_by_id(user.role_id) if get_role_by_id else None
                    user._role = role_snapshot
                    if role_snapshot:
                        logger.info(f"[DB:User] get_user_by_id({user_id}) pinned role snapshot: role_id={user.role_id}, role_name={role_snapshot.name}, use_api_openai_whisper={role_snapshot.use_api_openai_whisper}")
                    else:
                        logger.warning(f"[DB:User] get_user_by_id({user_id}) failed to load role snapshot for role_id={user.role_id}")
                except Exception as pin_err:
                    logger.error(f"[DB:User] Failed to pin role snapshot for user {user_id}: {pin_err}", exc_info=True)
        else:
            logger.warning(f"[DB:User] get_user_by_id({user_id}) - No row found in database")
    except MySQLError as err:
        logger.error(f"[DB:User] Error retrieving user by ID '{user_id}': {err}", exc_info=True)
        user = None # Ensure user is None on error
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return user

def get_user_by_oauth(provider: str, provider_id: str) -> Optional[User]:
    sql = 'SELECT * FROM users WHERE oauth_provider = %s AND oauth_provider_id = %s'
    cursor = None
    user = None
    try:
        cursor = get_cursor()
        cursor.execute(sql, (provider, provider_id))
        row = cursor.fetchone()
        user = _map_row_to_user(row)
        logger.debug(f"[DB:User] Searched for user by OAuth '{provider}/{provider_id}'. Found: {'Yes' if user else 'No'}")
    except MySQLError as err:
        logger.error(f"[DB:User] Error retrieving user by OAuth '{provider}/{provider_id}': {err}", exc_info=True)
        user = None # Ensure user is None on error
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return user

def link_oauth_to_user(user_id: int, oauth_provider: str, oauth_provider_id: str) -> bool:
    sql = 'UPDATE users SET oauth_provider = %s, oauth_provider_id = %s WHERE id = %s'
    cursor = get_cursor()
    try:
        cursor.execute(sql, (oauth_provider, oauth_provider_id, user_id))
        get_db().commit()
        logger.info(f"[DB:User] Linked OAuth provider '{oauth_provider}' to user ID {user_id}.")
        return True
    except MySQLError as err:
        logger.error(f"[DB:User] Error linking OAuth provider '{oauth_provider}' to user ID {user_id}: {err}", exc_info=True)
        get_db().rollback()
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def update_user_api_keys(user_id: int, encrypted_keys_json: Optional[str]) -> bool:
    sql = 'UPDATE users SET api_keys_encrypted = %s WHERE id = %s'
    cursor = get_cursor()
    try:
        cursor.execute(sql, (encrypted_keys_json, user_id))
        get_db().commit()
        logger.info(f"[DB:User] Updated API keys for user ID {user_id}.")
        return True
    except MySQLError as err:
        logger.error(f"[DB:User] Error updating API keys for user ID {user_id}: {err}", exc_info=True)
        get_db().rollback()
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def get_all_users() -> List[User]:
    sql = 'SELECT * FROM users ORDER BY username'
    users = []
    cursor = get_cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        users = [user for row in rows if (user := _map_row_to_user(row)) is not None]
        logger.debug(f"[DB:User] Retrieved {len(users)} users.")
    except MySQLError as err:
        logger.error(f"[DB:User] Error retrieving all users: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return users

def delete_user_by_id(user_id: int) -> bool:
    sql = 'DELETE FROM users WHERE id = %s'
    cursor = get_cursor()
    try:
        cursor.execute(sql, (user_id,))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.info(f"[DB:User] Deleted user with ID {user_id}.")
            return True
        else:
            logger.warning(f"[DB:User] Attempted to delete non-existent user with ID {user_id}.")
            return False
    except MySQLError as err:
        logger.error(f"[DB:User] Error deleting user with ID {user_id}: {err}", exc_info=True)
        get_db().rollback()
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def update_user_password_hash(user_id: int, new_password_hash: str) -> bool:
    sql = 'UPDATE users SET password_hash = %s WHERE id = %s'
    cursor = get_cursor()
    try:
        cursor.execute(sql, (new_password_hash, user_id))
        get_db().commit()
        logger.info(f"[DB:User] Updated password hash for user ID {user_id}.")
        return True
    except MySQLError as err:
        logger.error(f"[DB:User] Error updating password hash for user ID {user_id}: {err}", exc_info=True)
        get_db().rollback()
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def update_user_role(user_id: int, new_role_id: int) -> bool:
    sql = 'UPDATE users SET role_id = %s WHERE id = %s'
    cursor = get_cursor()

    # Diagnostics: capture previous role mapping for this user
    prev_role_id = None
    prev_role_name = None
    try:
        prev_user = get_user_by_id(user_id)
        if prev_user:
            prev_role_id = prev_user.role_id
            try:
                prev_role_name = getattr(prev_user.role, 'name', None)
            except Exception:
                prev_role_name = None
    except Exception as diag_err:
        logger.debug(f"[DB:User] update_user_role pre-fetch failed for user {user_id}: {diag_err}", exc_info=True)

    logger.info(f"[DB:User] ROLE_UPDATE: Updating user {user_id} from role_id={prev_role_id}:{prev_role_name} to role_id={new_role_id}")

    try:
        cursor.execute(sql, (new_role_id, user_id))
        get_db().commit()

        # Resolve new role name for diagnostics
        new_role_name = None
        new_role_permissions = {}
        try:
            new_role = get_role_by_id(new_role_id) if new_role_id is not None else None
            if new_role:
                new_role_name = new_role.name
                new_role_permissions = {
                    'use_api_openai_whisper': new_role.use_api_openai_whisper,
                    'allow_workflows': new_role.allow_workflows,
                    'allow_auto_title_generation': new_role.allow_auto_title_generation
                }
        except Exception as name_err:
            logger.debug(f"[DB:User] update_user_role post-fetch failed to resolve role name for role_id {new_role_id}: {name_err}", exc_info=True)

        logger.info(f"[DB:User] ROLE_UPDATE: Updated user {user_id}: {prev_role_id}:{prev_role_name} -> {new_role_id}:{new_role_name}, permissions={new_role_permissions}")
        
        # Verify the update took effect
        verify_user = get_user_by_id(user_id)
        if verify_user:
            logger.info(f"[DB:User] ROLE_UPDATE: Verification - user {user_id} now has role_id={verify_user.role_id}")
        
        return True
    except MySQLError as err:
        logger.error(f"[DB:User] Error updating role ID for user ID {user_id}: {err}", exc_info=True)
        get_db().rollback()
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

# --- Profile Update Functions ---

def update_user_profile(user_id: int, username: str, email: str, first_name: Optional[str], last_name: Optional[str]) -> bool:
    """
    Updates the core profile information (username, email, names) for a user.
    Does NOT handle uniqueness checks here; that should be done in the service layer before calling this.
    """
    sql = '''
        UPDATE users
        SET username = %s, email = %s, first_name = %s, last_name = %s
        WHERE id = %s
    '''
    cursor = get_cursor()
    try:
        cursor.execute(sql, (username, email, first_name, last_name, user_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.info(f"[DB:User:{user_id}] Updated core profile information (username, email, names).")
            return True
        else:
            logger.warning(f"[DB:User:{user_id}] Attempted to update profile for non-existent user or no changes made.")
            return False
    except MySQLError as err:
        get_db().rollback()
        if err.errno == 1062:
            if 'users.username' in err.msg or 'idx_username' in err.msg:
                 logger.warning(f"[DB:User:{user_id}] Profile update failed: Username '{username}' is already taken.")
            elif 'users.email' in err.msg or 'idx_email' in err.msg:
                 logger.warning(f"[DB:User:{user_id}] Profile update failed: Email '{email}' is already taken.")
            else:
                 logger.warning(f"[DB:User:{user_id}] Profile update failed due to duplicate entry: {err}")
            return False
        else:
            logger.error(f"[DB:User:{user_id}] Error updating profile: {err}", exc_info=True)
            return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def update_user_preferences(user_id: int, default_language: Optional[str], default_model: Optional[str], enable_auto_title_generation: Optional[bool] = None, language: Optional[str] = None) -> bool:
    """
    Updates the user's default language, transcription model, and auto-title preferences.
    """
    log_prefix = f"[DB:User:{user_id}]"
    set_clauses = []
    params = []

    if default_language is not None:
        set_clauses.append("default_content_language = %s")
        params.append(default_language if default_language else None)

    if default_model is not None:
        set_clauses.append("default_transcription_model = %s")
        params.append(default_model if default_model else None)

    if enable_auto_title_generation is not None:
        set_clauses.append("enable_auto_title_generation = %s")
        params.append(bool(enable_auto_title_generation)) # Ensure boolean

    if language is not None:
        set_clauses.append("language = %s")
        params.append(language if language else None)

    if not set_clauses:
        logger.debug(f"{log_prefix} No preference fields provided for update.")
        return False # Nothing to update

    sql = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = %s"
    params.append(user_id)

    cursor = get_cursor()
    try:
        cursor.execute(sql, tuple(params))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.info(f"{log_prefix} Updated preferences. Clauses: {set_clauses}")
            return True
        else:
            logger.warning(f"{log_prefix} Attempted to update preferences for non-existent user or no changes made.")
            return False
    except MySQLError as err:
        get_db().rollback()
        logger.error(f"{log_prefix} Error updating preferences: {err}", exc_info=True)
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

# --- NEW: Function to count users by role_id ---
def count_users_by_role_id(role_id: int) -> int:
    """Counts the number of users assigned to a specific role ID."""
    sql = "SELECT COUNT(*) as count FROM users WHERE role_id = %s"
    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql, (role_id,))
        result = cursor.fetchone()
        if result:
            count = result['count']
        logger.debug(f"[DB:User] Counted {count} users for role_id {role_id}.")
    except MySQLError as err:
        logger.error(f"[DB:User] Error counting users by role_id {role_id}: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count
# --- END NEW ---
