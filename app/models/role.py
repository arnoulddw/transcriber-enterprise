# app/models/role.py
# Defines the Role model, permissions, and related database functions, including monthly usage tracking.

import logging
import os
from flask import current_app
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from mysql.connector import Error as MySQLError
from app.database import get_db, get_cursor

# ----- Helper Functions -----

def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"SHOW COLUMNS FROM {table} LIKE %s", (column,))
    exists = cursor.fetchone() is not None
    cursor.fetchall()  # consume remaining results
    return exists

def _ensure_column(cursor, table: str, old_col: Optional[str], new_col: str, col_def: str, after: Optional[str] = None, log_prefix: str = "") -> None:
    if old_col and _column_exists(cursor, table, old_col):
        logging.info(f"{log_prefix} Found old '{old_col}' column. Renaming to '{new_col}'.")
        cursor.execute(f"ALTER TABLE {table} CHANGE COLUMN {old_col} {new_col} {col_def}")
    elif not _column_exists(cursor, table, new_col):
        extra = ""
        if after and "AFTER" not in col_def:
            extra = f" AFTER {after}"
        logging.info(f"{log_prefix} Adding '{new_col}' column ({col_def}{extra}).")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {new_col} {col_def}{extra}")

def _convert_role_field(col: str, value: Any) -> Any:
    if isinstance(value, bool):
        return 1 if value else 0
    elif value is None and col.startswith(('max_', 'history_')):
        return 0
    return value

def _prepare_role_fields(data: Dict[str, Any], fields: List[str]) -> Tuple[List[str], List[Any]]:
    columns = []
    values = []
    for col in fields:
        key = col
        # handle renamed limit keys
        if col == 'max_minutes_monthly' and 'max_seconds_monthly' in data:
            key = 'max_seconds_monthly'
        elif col == 'max_minutes_total' and 'max_seconds_total' in data:
            key = 'max_seconds_total'
        if key in data:
            columns.append(col)
            values.append(_convert_role_field(col, data[key]))
    return columns, values

def _normalize_usage_row(row: Dict[str, Any]) -> Dict[str, Any]:
    row['minutes_count'] = float(row.get('minutes_count') or 0.0)
    row['workflow_count'] = int(row.get('workflow_count') or 0)
    return row

def _safe_close(cursor, log_prefix: str = ""):
    if cursor:
        # The cursor is managed by the application context, so we don't close it here.
        pass

# ----- Role Model Definition -----

class Role:
    id: int
    name: str
    description: Optional[str]
    # Transcription API Permissions
    use_api_assemblyai: bool
    use_api_openai_whisper: bool
    use_api_openai_gpt_4o_transcribe: bool
    # --- MODIFIED: Added use_api_google_gemini ---
    use_api_google_gemini: bool
    # --- END MODIFIED ---
    # Feature Permissions
    access_admin_panel: bool
    allow_large_files: bool
    allow_context_prompt: bool
    allow_api_key_management: bool
    allow_download_transcript: bool
    allow_workflows: bool
    manage_workflow_templates: bool
    allow_auto_title_generation: bool
    # Usage Limits
    limit_daily_cost: float
    limit_weekly_cost: float
    limit_monthly_cost: float
    limit_daily_minutes: int
    limit_weekly_minutes: int
    limit_monthly_minutes: int
    limit_daily_workflows: int
    limit_weekly_workflows: int
    limit_monthly_workflows: int
    # History Limits
    max_history_items: int
    history_retention_days: int
    # Timestamps
    created_at: str
    updated_at: str

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.name = kwargs.get('name')
        self.description = kwargs.get('description')
        # Process boolean fields
        # --- MODIFIED: Added use_api_google_gemini to bool_fields ---
        bool_fields = [
            'use_api_assemblyai', 'use_api_openai_whisper', 'use_api_openai_gpt_4o_transcribe',
            'use_api_google_gemini', # Added
            'access_admin_panel', 'allow_large_files', 'allow_context_prompt',
            'allow_api_key_management', 'allow_download_transcript', 'allow_workflows',
            'manage_workflow_templates', 'allow_auto_title_generation'
        ]
        # --- END MODIFIED ---
        defaults = {field: (1 if field == 'allow_download_transcript' else 0) for field in bool_fields}
        for field in bool_fields:
            setattr(self, field, bool(kwargs.get(field, defaults[field])))
        # Process integer limit fields
        int_fields = [
            'limit_daily_minutes', 'limit_weekly_minutes', 'limit_monthly_minutes',
            'limit_daily_workflows', 'limit_weekly_workflows', 'limit_monthly_workflows',
            'max_history_items', 'history_retention_days'
        ]
        for field in int_fields:
            setattr(self, field, int(kwargs.get(field, 0)))

        float_fields = [
            'limit_daily_cost', 'limit_weekly_cost', 'limit_monthly_cost'
        ]
        for field in float_fields:
            setattr(self, field, float(kwargs.get(field, 0.0)))
        # Timestamps
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')

    def __repr__(self):
        return f'<Role {self.name} (ID: {self.id})>'

    def has_permission(self, permission_name: str) -> bool:
        # --- MODIFIED: Added use_api_google_gemini to valid prefixes (implicitly handled by use_) ---
        if not permission_name.startswith(('use_', 'allow_', 'access_', 'manage_')):
        # --- END MODIFIED ---
            logging.warning(f"Attempted to check non-boolean permission '{permission_name}' with has_permission().")
            return False
        return getattr(self, permission_name, False)

    def get_limit(self, limit_name: str) -> int | float:
        if not limit_name.startswith(('limit_', 'max_', 'history_')):
            logging.warning(f"Attempted to get non-limit permission '{limit_name}' with get_limit().")
            return 0
        return getattr(self, limit_name, 0)

# ----- Database Interaction Functions -----

def _map_row_to_role(row: Dict[str, Any]) -> Optional[Role]:
    if row:
        if 'max_seconds_monthly' in row:
            row['max_minutes_monthly'] = row.pop('max_seconds_monthly')
        if 'max_seconds_total' in row:
            row['max_minutes_total'] = row.pop('max_seconds_total')
        # --- MODIFIED: Ensure use_api_google_gemini is present ---
        if 'use_api_google_gemini' not in row:
            row['use_api_google_gemini'] = 0
        # --- END MODIFIED ---
        if 'allow_auto_title_generation' not in row:
            row['allow_auto_title_generation'] = 0
        return Role(**row)
    return None

def init_roles_table() -> None:
    cursor = get_cursor()
    log_prefix = "[DB:Schema:MySQL]"
    logging.info(f"{log_prefix} Checking/Initializing 'roles' table...")
    try:
        # --- MODIFIED: Added use_api_google_gemini ---
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS roles (
                id INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(80) UNIQUE NOT NULL,
                description TEXT,
                use_api_assemblyai BOOLEAN NOT NULL DEFAULT FALSE,
                use_api_openai_whisper BOOLEAN NOT NULL DEFAULT FALSE,
                use_api_openai_gpt_4o_transcribe BOOLEAN NOT NULL DEFAULT FALSE,
                use_api_google_gemini BOOLEAN NOT NULL DEFAULT FALSE,
                access_admin_panel BOOLEAN NOT NULL DEFAULT FALSE,
                allow_large_files BOOLEAN NOT NULL DEFAULT FALSE,
                allow_context_prompt BOOLEAN NOT NULL DEFAULT FALSE,
                allow_api_key_management BOOLEAN NOT NULL DEFAULT FALSE,
                allow_download_transcript BOOLEAN NOT NULL DEFAULT TRUE,
                allow_workflows BOOLEAN NOT NULL DEFAULT FALSE,
                manage_workflow_templates BOOLEAN NOT NULL DEFAULT FALSE,
                allow_auto_title_generation BOOLEAN NOT NULL DEFAULT FALSE,
                limit_daily_cost DECIMAL(10, 4) NOT NULL DEFAULT 0.0000,
                limit_weekly_cost DECIMAL(10, 4) NOT NULL DEFAULT 0.0000,
                limit_monthly_cost DECIMAL(10, 4) NOT NULL DEFAULT 0.0000,
                limit_daily_minutes INT NOT NULL DEFAULT 0,
                limit_weekly_minutes INT NOT NULL DEFAULT 0,
                limit_monthly_minutes INT NOT NULL DEFAULT 0,
                limit_daily_workflows INT NOT NULL DEFAULT 0,
                limit_weekly_workflows INT NOT NULL DEFAULT 0,
                limit_monthly_workflows INT NOT NULL DEFAULT 0,
                max_history_items INT NOT NULL DEFAULT 0,
                history_retention_days INT NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                INDEX idx_role_name (name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            '''
        )
        # --- END MODIFIED ---
        _ensure_column(cursor, "roles", "max_seconds_monthly", "max_minutes_monthly",
                       "INT NOT NULL DEFAULT 0", after="max_transcriptions_monthly", log_prefix=log_prefix)
        _ensure_column(cursor, "roles", "max_seconds_total", "max_minutes_total",
                       "INT NOT NULL DEFAULT 0", after="max_transcriptions_total", log_prefix=log_prefix)
        new_workflow_columns = {
            'allow_workflows': "BOOLEAN NOT NULL DEFAULT FALSE AFTER allow_download_transcript",
            'manage_workflow_templates': "BOOLEAN NOT NULL DEFAULT FALSE AFTER allow_workflows",
            'max_workflows_monthly': "INT NOT NULL DEFAULT 0 AFTER max_minutes_total",
            'max_workflows_total': "INT NOT NULL DEFAULT 0 AFTER max_workflows_monthly"
        }
        for col_name, col_def in new_workflow_columns.items():
            _ensure_column(cursor, "roles", None, col_name, col_def, log_prefix=log_prefix)

        _ensure_column(cursor, "roles", None, "allow_auto_title_generation",
                       "BOOLEAN NOT NULL DEFAULT FALSE", after="manage_workflow_templates", log_prefix=log_prefix)

        # --- MODIFIED: Add use_api_google_gemini column idempotently ---
        _ensure_column(cursor, "roles", None, "use_api_google_gemini",
                       "BOOLEAN NOT NULL DEFAULT FALSE", after="use_api_openai_gpt_4o_transcribe", log_prefix=log_prefix)
        # --- END MODIFIED ---

        get_db().commit()
        logging.info(f"{log_prefix} 'roles' table schema verified/initialized.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error during 'roles' table initialization: {err}", exc_info=True)
        get_db().rollback()
        raise
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

# This function is no longer needed as the 'monthly_usage' table has been removed.

def create_role(name: str, description: Optional[str] = None, permissions: Optional[Dict[str, Any]] = None) -> Optional[Role]:
    """
    Creates a new role in the database.
    Handles renamed limit fields and new workflow fields.
    """
    if permissions is None:
        permissions = {}
    # --- MODIFIED: Add use_api_google_gemini to valid columns ---
    valid_permission_columns = [
        'use_api_assemblyai', 'use_api_openai_whisper', 'use_api_openai_gpt_4o_transcribe',
        'use_api_google_gemini', # Added
        'access_admin_panel', 'allow_large_files', 'allow_context_prompt',
        'allow_api_key_management', 'allow_download_transcript',
        'allow_workflows', 'manage_workflow_templates', 'allow_auto_title_generation',
        'limit_daily_cost', 'limit_weekly_cost', 'limit_monthly_cost',
        'limit_daily_minutes', 'limit_weekly_minutes', 'limit_monthly_minutes',
        'limit_daily_workflows', 'limit_weekly_workflows', 'limit_monthly_workflows',
        'max_history_items', 'history_retention_days'
    ]
    # --- END MODIFIED ---
    base_columns = ['name', 'description']
    base_values = [name, description]
    new_columns, new_values = _prepare_role_fields(permissions, valid_permission_columns)
    sql_columns = base_columns + new_columns
    sql_values = base_values + new_values
    placeholders = ['%s'] * len(sql_values)
    sql = f"INSERT INTO roles ({', '.join(sql_columns)}, created_at, updated_at) VALUES ({', '.join(placeholders)}, NOW(), NOW())"
    cursor = get_cursor()
    try:
        cursor.execute(sql, tuple(sql_values))
        get_db().commit()
        role_id = cursor.lastrowid
        logging.info(f"[DB:Role] Created new role '{name}' with ID {role_id}.")
        return get_role_by_id(role_id)
    except MySQLError as err:
        get_db().rollback()
        if err.errno == 1062:
            logging.warning(f"[DB:Role] Attempted to create role with duplicate name: {name}")
        else:
            logging.error(f"[DB:Role] Error creating role '{name}': {err}", exc_info=True)
        return None
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def get_role_by_id(role_id: int) -> Optional[Role]:
    sql = 'SELECT * FROM roles WHERE id = %s'
    cursor = None
    role = None
    try:
        cursor = get_cursor()
        cursor.execute(sql, (role_id,))
        row = cursor.fetchone()
        role = _map_row_to_role(row)
    except MySQLError as err:
        logging.error(f"[DB:Role] Error retrieving role by ID '{role_id}': {err}", exc_info=True)
        role = None # Ensure role is None on error
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return role

def get_role_by_name(name: str) -> Optional[Role]:
    sql = 'SELECT * FROM roles WHERE name = %s'
    cursor = None
    role = None
    try:
        cursor = get_cursor()
        cursor.execute(sql, (name,))
        row = cursor.fetchone()
        role = _map_row_to_role(row)
    except MySQLError as err:
        logging.error(f"[DB:Role] Error retrieving role by name '{name}': {err}", exc_info=True)
        role = None # Ensure role is None on error
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return role

def get_all_roles() -> List[Role]:
    sql = 'SELECT * FROM roles ORDER BY name'
    roles = []
    cursor = get_cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        roles = [_map_row_to_role(row) for row in rows if row]
        logging.debug(f"[DB:Role] Retrieved {len(roles)} roles.")
    except MySQLError as err:
        logging.error(f"[DB:Role] Error retrieving all roles: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return roles

# This function is no longer needed as the 'monthly_usage' table has been removed.

def increment_usage(user_id: int, cost: float, minutes_processed: float) -> None:
    """
    Increments usage stats for a user after a transcription.
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime('%Y-%m-%d')
    log_prefix = f"[DB:Usage:User:{user_id}]"
    
    cursor = get_cursor()
    try:
        sql = """
            INSERT INTO user_usage (user_id, date, cost, minutes, workflows)
            VALUES (%s, %s, %s, %s, 0)
            ON DUPLICATE KEY UPDATE
            cost = cost + VALUES(cost),
            minutes = minutes + VALUES(minutes)
        """
        cursor.execute(sql, (user_id, date_str, cost, minutes_processed))
        get_db().commit()
        logging.debug(f"{log_prefix} Successfully incremented usage stats.")
    except MySQLError as e:
        logging.error(f"{log_prefix} Error incrementing usage stats: {e}", exc_info=True)
        get_db().rollback()
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def increment_workflow_usage(user_id: int) -> None:
    """
    Increments workflow usage stats for a user.
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime('%Y-%m-%d')
    log_prefix = f"[DB:Usage:Workflow:User:{user_id}]"
    cursor = get_cursor()
    try:
        sql = """
            INSERT INTO user_usage (user_id, date, cost, minutes, workflows)
            VALUES (%s, %s, 0, 0, 1)
            ON DUPLICATE KEY UPDATE
            workflows = workflows + 1
        """
        cursor.execute(sql, (user_id, date_str))
        get_db().commit()
        logging.debug(f"{log_prefix} Successfully incremented workflow usage stats.")
    except MySQLError as e:
        logging.error(f"{log_prefix} Error incrementing workflow usage stats: {e}", exc_info=True)
        get_db().rollback()
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def update_role(role_id: int, role_data: Dict[str, Any]) -> bool:
    """
    Updates an existing role in the database.
    Handles renamed limit fields and new workflow fields.
    """
    log_prefix = f"[DB:Role:Update:{role_id}]"
    # --- MODIFIED: Add use_api_google_gemini to updatable columns ---
    updatable_columns = [
        'name', 'description',
        'use_api_assemblyai', 'use_api_openai_whisper', 'use_api_openai_gpt_4o_transcribe',
        'use_api_google_gemini', # Added
        'access_admin_panel', 'allow_large_files', 'allow_context_prompt',
        'allow_api_key_management', 'allow_download_transcript',
        'allow_workflows', 'manage_workflow_templates', 'allow_auto_title_generation',
        'limit_daily_cost', 'limit_weekly_cost', 'limit_monthly_cost',
        'limit_daily_minutes', 'limit_weekly_minutes', 'limit_monthly_minutes',
        'limit_daily_workflows', 'limit_weekly_workflows', 'limit_monthly_workflows',
        'max_history_items', 'history_retention_days'
    ]
    # --- END MODIFIED ---
    set_clauses = []
    sql_values = []
    new_columns, new_values = _prepare_role_fields(role_data, updatable_columns)
    for col, value in zip(new_columns, new_values):
        set_clauses.append(f"{col} = %s")
        sql_values.append(value)
    set_clauses.append("updated_at = %s")
    sql_values.append(datetime.now(timezone.utc))
    sql_values.append(role_id)
    if not set_clauses or len(set_clauses) == 1:  # Only updated_at added
        logging.warning(f"{log_prefix} No valid fields provided for update.")
        return False
    sql = f"UPDATE roles SET {', '.join(set_clauses)} WHERE id = %s"
    cursor = get_cursor()
    try:
        cursor.execute(sql, tuple(sql_values))
        get_db().commit()
        if cursor.rowcount > 0:
            logging.info(f"{log_prefix} Role updated successfully.")
            return True
        else:
            role = get_role_by_id(role_id)
            if role:
                logging.warning(f"{log_prefix} Role update query executed but no rows affected (data might be unchanged).")
                return True
            else:
                logging.warning(f"{log_prefix} Role update failed: Role with ID {role_id} not found.")
                return False
    except MySQLError as err:
        get_db().rollback()
        if err.errno == 1062:
            logging.warning(f"{log_prefix} Role update failed due to duplicate name: {role_data.get('name')}")
        else:
            logging.error(f"{log_prefix} Error updating role: {err}", exc_info=True)
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def delete_role(role_id: int) -> Tuple[bool, str]:
    """
    Deletes a role from the database after performing safety checks.

    Args:
        role_id: The ID of the role to delete.

    Returns:
        A tuple: (success: bool, message: str).
    """
    log_prefix = f"[DB:Role:Delete:{role_id}]"
    cursor = None
    delete_cursor = None
    try:
        cursor = get_cursor()
        cursor.execute("SELECT name FROM roles WHERE id = %s", (role_id,))
        role_row = cursor.fetchone()
        if not role_row:
            logging.warning(f"{log_prefix} Role not found.")
            return False, "Role not found."
        role_name = role_row['name']
        if role_name in ['admin', 'beta-tester']:
            logging.warning(f"{log_prefix} Attempt to delete protected default role '{role_name}'.")
            return False, f"Cannot delete protected default role '{role_name}'."
        cursor.execute("SELECT COUNT(*) as user_count FROM users WHERE role_id = %s", (role_id,))
        user_count_row = cursor.fetchone()
        cursor.fetchall()  # Consume remaining results
        user_count = user_count_row['user_count'] if user_count_row else 0
        if user_count > 0:
            logging.warning(f"{log_prefix} Cannot delete role '{role_name}' as {user_count} user(s) are assigned to it.")
            return False, f"Cannot delete role '{role_name}' as {user_count} user(s) are assigned to it. Reassign users first."
        delete_cursor = get_cursor()
        delete_cursor.execute("DELETE FROM roles WHERE id = %s", (role_id,))
        get_db().commit()
        if delete_cursor.rowcount > 0:
            logging.info(f"{log_prefix} Role '{role_name}' deleted successfully.")
            return True, f"Role '{role_name}' deleted successfully."
        else:
            logging.error(f"{log_prefix} Delete query executed but no rows affected for role '{role_name}'.")
            return False, "Role deletion failed unexpectedly after checks."
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error deleting role: {err}", exc_info=True)
        return False, "Database error occurred during role deletion."
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
def init_user_usage_table() -> None:
    cursor = get_cursor()
    log_prefix = "[DB:Schema:MySQL]"
    logging.info(f"{log_prefix} Checking/Initializing 'user_usage' table...")
    try:
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS user_usage (
                id INT PRIMARY KEY AUTO_INCREMENT,
                user_id INT NOT NULL,
                date DATE NOT NULL,
                cost DECIMAL(10, 4) NOT NULL DEFAULT 0.0000,
                minutes INT NOT NULL DEFAULT 0,
                workflows INT NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                UNIQUE KEY uk_user_date (user_id, date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            '''
        )
        get_db().commit()
        logging.info(f"{log_prefix} 'user_usage' table schema verified/initialized.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error during 'user_usage' table initialization:. {err}", exc_info=True)
        get_db().rollback()
        raise
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass