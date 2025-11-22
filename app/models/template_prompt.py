# app/models/template_prompt.py
# Defines the TemplatePrompt model and database interaction functions for MySQL.

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

# Import MySQL specific error class
from mysql.connector import Error as MySQLError

# Import centralized DB functions
from app.database import get_db, get_cursor

# --- TemplatePrompt Class Definition (Optional but good practice) ---
class TemplatePrompt:
    id: int
    title: str
    prompt_text: str
    language: Optional[str]
    # --- ADDED: color attribute ---
    color: str # Store as hex string, e.g., '#ffffff'
    # --- END ADDED ---
    created_at: str
    updated_at: str

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.title = kwargs.get('title')
        self.prompt_text = kwargs.get('prompt_text')
        self.language = kwargs.get('language') # Can be None
        # --- ADDED: Initialize color, default to white ---
        self.color = kwargs.get('color', '#ffffff')
        # --- END ADDED ---
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')
        # Usage metrics are optional and default to zero when not supplied
        self.unique_user_count = int(kwargs.get('unique_user_count', 0) or 0)
        self.total_usage_count = int(kwargs.get('total_usage_count', 0) or 0)

    def __repr__(self):
        lang_info = f"Lang:{self.language}" if self.language else "Lang:All"
        # --- MODIFIED: Include color in repr ---
        return f'<TemplatePrompt {self.id} ({lang_info}, Color:{self.color}, Title: {self.title[:30]}...)>'
        # --- END MODIFIED ---

# --- Database Schema Initialization ---

def init_db_command() -> None:
    """Initializes the 'template_prompts' table schema."""
    cursor = get_cursor()
    log_prefix = "[DB:Schema:MySQL]"
    logging.info(f"{log_prefix} Checking/Initializing 'template_prompts' table...")
    try:
        # --- MODIFIED: Added 'color' column ---
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS template_prompts (
                id INT PRIMARY KEY AUTO_INCREMENT,
                title VARCHAR(100) NOT NULL,
                prompt_text TEXT NOT NULL,
                language VARCHAR(10) DEFAULT NULL, -- NULL means applicable to all languages
                color VARCHAR(7) NOT NULL DEFAULT '#ffffff', -- Added color column, default white
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_template_prompt_language (language)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            '''
        )
        # --- END MODIFIED ---

        # --- Idempotent ALTER TABLE for color column ---
        cursor.execute("SHOW COLUMNS FROM template_prompts LIKE 'color'")
        color_col_exists = cursor.fetchone()
        cursor.fetchall() # Consume remaining results
        if not color_col_exists:
            logging.info(f"{log_prefix} Adding 'color' column (VARCHAR(7)) to 'template_prompts' table.")
            # Add after language column
            cursor.execute("ALTER TABLE template_prompts ADD COLUMN color VARCHAR(7) NOT NULL DEFAULT '#ffffff' AFTER language")
        # --- End ALTER TABLE ---

        cursor.execute("SHOW COLUMNS FROM template_prompts LIKE 'created_at'")
        created_at_col = cursor.fetchone()
        cursor.fetchall()
        created_at_type = (created_at_col.get('Type') if isinstance(created_at_col, dict) else (created_at_col[1] if created_at_col else "")).lower()
        if created_at_col and 'timestamp' not in created_at_type:
            logging.info(f"{log_prefix} Converting 'created_at' column on 'template_prompts' table to TIMESTAMP.")
            cursor.execute("ALTER TABLE template_prompts MODIFY COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")

        cursor.execute("SHOW COLUMNS FROM template_prompts LIKE 'updated_at'")
        updated_at_col = cursor.fetchone()
        cursor.fetchall()
        updated_at_type = (updated_at_col.get('Type') if isinstance(updated_at_col, dict) else (updated_at_col[1] if updated_at_col else "")).lower()
        if updated_at_col and 'timestamp' not in updated_at_type:
            logging.info(f"{log_prefix} Converting 'updated_at' column on 'template_prompts' table to TIMESTAMP.")
            cursor.execute("ALTER TABLE template_prompts MODIFY COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")

        get_db().commit()
        logging.info(f"{log_prefix} 'template_prompts' table schema verified/initialized.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error during 'template_prompts' table initialization: {err}", exc_info=True)
        get_db().rollback()
        raise
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

# --- Helper Function ---

def _map_row_to_template_prompt(row: Dict[str, Any]) -> Optional[TemplatePrompt]:
    """Maps a database row (dictionary) to a TemplatePrompt object."""
    if row:
        # --- ADDED: Ensure color has a default if somehow NULL in DB ---
        if 'color' not in row or row['color'] is None:
            row['color'] = '#ffffff'
        # --- END ADDED ---
        return TemplatePrompt(**row)
    return None

# --- CRUD Operations ---

# --- MODIFIED: Add color parameter ---
def add_template(title: str, prompt_text: str, language: Optional[str] = None, color: str = '#ffffff') -> Optional[TemplatePrompt]:
    """Adds a new template prompt."""
    log_prefix = "[DB:TemplatePrompt]"
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    sql = '''
        INSERT INTO template_prompts (title, prompt_text, language, color, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        '''
    # --- END MODIFIED ---
    cursor = get_cursor()
    try:
        # Ensure language is None if empty string is passed
        lang_to_store = language if language else None
        # Ensure color is valid hex or default to white
        color_to_store = color if (color and color.startswith('#') and len(color) == 7) else '#ffffff'

        # --- MODIFIED: Pass color_to_store ---
        cursor.execute(sql, (title, prompt_text, lang_to_store, color_to_store, now_utc, now_utc))
        # --- END MODIFIED ---
        get_db().commit()
        prompt_id = cursor.lastrowid
        logging.info(f"{log_prefix} Added new template prompt '{title}' (Lang: {lang_to_store or 'All'}, Color: {color_to_store}) with ID {prompt_id}.")
        # Construct object directly
        if prompt_id:
            return TemplatePrompt(
                id=prompt_id,
                title=title,
                prompt_text=prompt_text,
                language=lang_to_store,
                color=color_to_store, # Include color
                created_at=now_utc.isoformat(),
                updated_at=now_utc.isoformat()
            )
        else:
            return None
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error adding template prompt '{title}': {err}", exc_info=True)
        return None
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def get_templates(language: Optional[str] = None) -> List[TemplatePrompt]:
    """
    Retrieves template prompts.
    If language is specified, filters by that language OR NULL (applicable to all).
    If language is None, retrieves ALL templates (for admin view).
    """
    log_prefix = "[DB:TemplatePrompt]"
    params: List[Any] = []
    sql = 'SELECT * FROM template_prompts' # Start with base query

    if language:
        # User view: Filter by specific language OR NULL (for 'All Languages' templates)
        sql += ' WHERE (language = %s OR language IS NULL)'
        params.append(language)
        log_prefix += f":Lang:{language}"
    # else: Admin view (language is None): No WHERE clause needed, fetch all

    sql += ' ORDER BY language, title ASC' # Order by language then title

    prompts = []
    cursor = get_cursor()
    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        prompts = [_map_row_to_template_prompt(row) for row in rows if row]
        logging.debug(f"{log_prefix} Retrieved {len(prompts)} template prompts.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving template prompts: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return prompts

def get_template_by_id(prompt_id: int) -> Optional[TemplatePrompt]:
    """Retrieves a specific template prompt by its ID."""
    log_prefix = f"[DB:TemplatePrompt:{prompt_id}]"
    sql = 'SELECT * FROM template_prompts WHERE id = %s'
    prompt = None
    cursor = get_cursor()
    try:
        cursor.execute(sql, (prompt_id,))
        row = cursor.fetchone()
        prompt = _map_row_to_template_prompt(row)
        if prompt:
            logging.debug(f"{log_prefix} Retrieved template prompt.")
        else:
            logging.debug(f"{log_prefix} Template prompt not found.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving template prompt: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return prompt


def get_template_usage_stats() -> Dict[int, Dict[str, int]]:
    """Returns workflow usage stats per template (total runs and unique users)."""
    log_prefix = "[DB:TemplatePrompt:UsageStats]"
    sql = """
        SELECT
            up.source_template_id AS template_id,
            COUNT(*) AS total_uses,
            COUNT(DISTINCT lo.user_id) AS unique_users
        FROM llm_operations lo
        INNER JOIN user_prompts up ON lo.prompt_id = up.id
        WHERE lo.operation_type = 'workflow'
          AND up.source_template_id IS NOT NULL
        GROUP BY up.source_template_id
    """
    cursor = get_cursor()
    stats: Dict[int, Dict[str, int]] = {}
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        for row in rows:
            template_id = row.get('template_id')
            if template_id is None:
                continue
            stats[int(template_id)] = {
                'total_uses': int(row.get('total_uses') or 0),
                'unique_users': int(row.get('unique_users') or 0)
            }
        logging.debug(f"{log_prefix} Retrieved usage stats for {len(stats)} templates.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving usage stats: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return stats

# --- MODIFIED: Add color parameter ---
def update_template(prompt_id: int, title: str, prompt_text: str, language: Optional[str] = None, color: str = '#ffffff') -> bool:
    """Updates an existing template prompt."""
    log_prefix = f"[DB:TemplatePrompt:{prompt_id}]"
    now_utc_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    sql = '''
        UPDATE template_prompts
        SET title = %s, prompt_text = %s, language = %s, color = %s, updated_at = %s
        WHERE id = %s
        '''
    # --- END MODIFIED ---
    cursor = get_cursor()
    try:
        lang_to_store = language if language else None
        # Ensure color is valid hex or default to white
        color_to_store = color if (color and color.startswith('#') and len(color) == 7) else '#ffffff'
        # --- MODIFIED: Pass color_to_store ---
        cursor.execute(sql, (title, prompt_text, lang_to_store, color_to_store, now_utc_iso, prompt_id))
        # --- END MODIFIED ---
        get_db().commit()
        if cursor.rowcount > 0:
            logging.info(f"{log_prefix} Updated template prompt '{title}' (Lang: {lang_to_store or 'All'}, Color: {color_to_store}).")
            return True
        else:
            logging.warning(f"{log_prefix} Update failed: Template prompt ID {prompt_id} not found or no changes made.")
            return False
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error updating template prompt '{title}': {err}", exc_info=True)
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def delete_template(prompt_id: int) -> bool:
    """Deletes a specific template prompt."""
    log_prefix = f"[DB:TemplatePrompt:{prompt_id}]"
    sql = 'DELETE FROM template_prompts WHERE id = %s'
    cursor = get_cursor()
    try:
        cursor.execute(sql, (prompt_id,))
        get_db().commit()
        if cursor.rowcount > 0:
            logging.info(f"{log_prefix} Deleted template prompt.")
            return True
        else:
            logging.warning(f"{log_prefix} Delete failed: Template prompt not found.")
            return False
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error deleting template prompt: {err}", exc_info=True)
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
