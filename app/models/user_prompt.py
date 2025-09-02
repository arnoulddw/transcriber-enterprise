# app/models/user_prompt.py
# Defines the UserPrompt model and database interaction functions for MySQL.

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

# Import MySQL specific error class
from mysql.connector import Error as MySQLError

# Import centralized DB functions
from app.database import get_db, get_cursor

# --- UserPrompt Class Definition (Optional but good practice) ---
class UserPrompt:
    id: int
    user_id: int
    title: str
    prompt_text: str
    color: str # Store as hex string, e.g., '#ffffff'
    source_template_id: Optional[int] # ID of the template_prompt this was copied from
    created_at: str
    updated_at: str

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.user_id = kwargs.get('user_id')
        self.title = kwargs.get('title')
        self.prompt_text = kwargs.get('prompt_text')
        self.color = kwargs.get('color', '#ffffff')
        self.source_template_id = kwargs.get('source_template_id')
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')

    def __repr__(self):
        source_info = f", SourceID:{self.source_template_id}" if self.source_template_id else ""
        return f'<UserPrompt {self.id} (User: {self.user_id}, Color:{self.color}{source_info}, Title: {self.title[:30]}...)>'

# --- Database Schema Initialization ---

def init_db_command() -> None:
    """Initializes the 'user_prompts' table schema."""
    cursor = get_cursor()
    log_prefix = "[DB:Schema:MySQL]"
    logging.info(f"{log_prefix} Checking/Initializing 'user_prompts' table...")
    try:
        # Dependency Check: Ensure 'users' and 'template_prompts' tables exist first
        cursor.execute("SHOW TABLES LIKE 'users'")
        if not cursor.fetchone():
            raise RuntimeError("User table must exist before user_prompts table can be initialized.")
        cursor.fetchall()
        cursor.execute("SHOW TABLES LIKE 'template_prompts'")
        if not cursor.fetchone():
            raise RuntimeError("Template Prompts table must exist before user_prompts table can be initialized.")
        cursor.fetchall()

        # --- MODIFIED: Use ON DELETE CASCADE for source_template_id ---
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS user_prompts (
                id INT PRIMARY KEY AUTO_INCREMENT,
                user_id INT NOT NULL,
                title VARCHAR(100) NOT NULL,
                prompt_text TEXT NOT NULL,
                color VARCHAR(7) NOT NULL DEFAULT '#ffffff',
                source_template_id INT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (source_template_id) REFERENCES template_prompts(id) ON DELETE CASCADE,
                INDEX idx_user_prompt_user (user_id),
                INDEX idx_user_prompt_source_template (source_template_id),
                INDEX idx_user_prompt_user_created (user_id, created_at(20))
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            '''
        )
        # --- END MODIFIED ---

        # --- Idempotent ALTER TABLE for color column ---
        cursor.execute("SHOW COLUMNS FROM user_prompts LIKE 'color'")
        color_col_exists = cursor.fetchone()
        cursor.fetchall()
        if not color_col_exists:
            logging.info(f"{log_prefix} Adding 'color' column (VARCHAR(7)) to 'user_prompts' table.")
            cursor.execute("ALTER TABLE user_prompts ADD COLUMN color VARCHAR(7) NOT NULL DEFAULT '#ffffff' AFTER prompt_text")

        # --- Idempotent ALTER TABLE for source_template_id column ---
        cursor.execute("SHOW COLUMNS FROM user_prompts LIKE 'source_template_id'")
        source_id_col_exists = cursor.fetchone()
        cursor.fetchall()
        if not source_id_col_exists:
            logging.info(f"{log_prefix} Adding 'source_template_id' column to 'user_prompts' table.")
            cursor.execute("ALTER TABLE user_prompts ADD COLUMN source_template_id INT DEFAULT NULL AFTER color")
            
            # --- MODIFIED: Reordered ADD INDEX and ADD CONSTRAINT, and use ON DELETE CASCADE ---
            logging.info(f"{log_prefix} Adding index for 'source_template_id' to 'user_prompts' table.")
            cursor.execute("ALTER TABLE user_prompts ADD INDEX idx_user_prompt_source_template (source_template_id)")
            
            logging.info(f"{log_prefix} Adding foreign key for 'source_template_id' to 'user_prompts' table.")
            cursor.execute("ALTER TABLE user_prompts ADD CONSTRAINT fk_source_template FOREIGN KEY (source_template_id) REFERENCES template_prompts(id) ON DELETE CASCADE")
            # --- END MODIFIED ---

        get_db().commit()
        logging.info(f"{log_prefix} 'user_prompts' table schema verified/initialized.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error during 'user_prompts' table initialization: {err}", exc_info=True)
        get_db().rollback()
        raise
    except RuntimeError as e:
        logging.error(f"{log_prefix} Initialization dependency error: {e}")
        get_db().rollback()
        raise
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

# --- Helper Function ---

def _map_row_to_user_prompt(row: Dict[str, Any]) -> Optional[UserPrompt]:
    """Maps a database row (dictionary) to a UserPrompt object."""
    if row:
        if 'color' not in row or row['color'] is None:
            row['color'] = '#ffffff'
        return UserPrompt(**row)
    return None

# --- CRUD Operations ---

def add_prompt(user_id: int, title: str, prompt_text: str, color: str = '#ffffff', source_template_id: Optional[int] = None) -> Optional[UserPrompt]:
    """Adds a new saved prompt for a user."""
    log_prefix = f"[DB:UserPrompt:User:{user_id}]"
    now_utc_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    sql = '''
        INSERT INTO user_prompts (user_id, title, prompt_text, color, source_template_id, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''

    logging.debug(f"{log_prefix} add_prompt received color='{color}' (type: {type(color)})")
    is_valid_color = False
    if isinstance(color, str):
        check1 = bool(color)
        check2 = color.startswith('#')
        check3 = len(color) == 7
        is_valid_color = check1 and check2 and check3
        logging.debug(f"{log_prefix} Color validation: bool(color)={check1}, startsWith('#')={check2}, len==7={check3} -> isValid={is_valid_color}")
    else:
        logging.warning(f"{log_prefix} Received color is not a string, defaulting to white.")
    
    color_to_store = color if is_valid_color else '#ffffff'
    logging.debug(f"{log_prefix} Color to store in DB: '{color_to_store}'")

    cursor = get_cursor()
    try:
        # Check for duplicate title
        cursor.execute("SELECT id FROM user_prompts WHERE user_id = %s AND title = %s", (user_id, title))
        if cursor.fetchone():
            logging.warning(f"{log_prefix} Prompt with title '{title}' already exists for this user.")
            raise MySQLError(errno=1062, msg="Duplicate entry")

        cursor.execute(sql, (user_id, title, prompt_text, color_to_store, source_template_id, now_utc_iso, now_utc_iso))
        get_db().commit()
        prompt_id = cursor.lastrowid
        logging.info(f"{log_prefix} Added new prompt '{title}' (Color: {color_to_store}, SourceID: {source_template_id}) with ID {prompt_id}.")
        return get_prompt_by_id(prompt_id, user_id)
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Database error adding prompt '{title}': {err}", exc_info=True)
        # Re-raise the exception so the service layer can handle it.
        raise
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def get_prompts_by_user(user_id: int) -> List[UserPrompt]:
    """Retrieves all saved prompts for a specific user, ordered by creation date descending."""
    log_prefix = f"[DB:UserPrompt:User:{user_id}]"
    sql = 'SELECT * FROM user_prompts WHERE user_id = %s ORDER BY created_at DESC'
    prompts = []
    cursor = get_cursor()
    try:
        cursor.execute(sql, (user_id,))
        rows = cursor.fetchall()
        prompts = [_map_row_to_user_prompt(row) for row in rows if row]
        logging.debug(f"{log_prefix} Retrieved {len(prompts)} saved prompts.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving prompts: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return prompts

def get_prompt_by_id(prompt_id: int, user_id: Optional[int] = None) -> Optional[UserPrompt]:
    """
    Retrieves a specific saved prompt by its ID.
    If user_id is provided, ensures the prompt belongs to that user.
    """
    sql = 'SELECT * FROM user_prompts WHERE id = %s'
    params: List[Any] = [prompt_id]
    log_prefix = f"[DB:UserPrompt:{prompt_id}]"
    if user_id is not None:
        sql += ' AND user_id = %s'
        params.append(user_id)
        log_prefix += f":User:{user_id}"

    prompt = None
    cursor = get_cursor()
    try:
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone()
        prompt = _map_row_to_user_prompt(row)
        if prompt:
            logging.debug(f"{log_prefix} Retrieved prompt.")
        else:
            logging.debug(f"{log_prefix} Prompt not found or ownership mismatch.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving prompt: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return prompt

def update_prompt(prompt_id: int, user_id: int, title: str, prompt_text: str, color: str = '#ffffff') -> bool:
    """Updates an existing saved prompt for a user."""
    log_prefix = f"[DB:UserPrompt:{prompt_id}:User:{user_id}]"
    now_utc_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    # --- MODIFIED: Do not update source_template_id on user edit ---
    sql = '''
        UPDATE user_prompts
        SET title = %s, prompt_text = %s, color = %s, updated_at = %s, source_template_id = NULL
        WHERE id = %s AND user_id = %s
        '''
    cursor = get_cursor()
    try:
        color_to_store = color if (color and isinstance(color, str) and color.startswith('#') and len(color) == 7) else '#ffffff'
        cursor.execute(sql, (title, prompt_text, color_to_store, now_utc_iso, prompt_id, user_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logging.info(f"{log_prefix} Updated prompt '{title}' (Color: {color_to_store}). Source link broken due to user edit.")
            return True
        else:
            cursor.execute("SELECT COUNT(*) as count FROM user_prompts WHERE id = %s", (prompt_id,))
            result = cursor.fetchone()
            prompt_exists = result['count'] > 0 if result else False
            if not prompt_exists:
                logging.warning(f"{log_prefix} Update failed: Prompt ID {prompt_id} not found.")
            else:
                logging.warning(f"{log_prefix} Update failed: Ownership mismatch or no changes made for prompt ID {prompt_id}.")
            return False
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error updating prompt '{title}': {err}", exc_info=True)
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def delete_prompt(prompt_id: int, user_id: int) -> bool:
    """Deletes a specific saved prompt for a user."""
    log_prefix = f"[DB:UserPrompt:{prompt_id}:User:{user_id}]"
    sql = 'DELETE FROM user_prompts WHERE id = %s AND user_id = %s'
    cursor = get_cursor()
    try:
        cursor.execute(sql, (prompt_id, user_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logging.info(f"{log_prefix} Deleted prompt.")
            return True
        else:
            logging.warning(f"{log_prefix} Delete failed: Prompt not found or ownership mismatch.")
            return False
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error deleting prompt: {err}", exc_info=True)
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

# --- NEW: Function to delete prompts by source template ---
def delete_prompts_by_source_id(source_template_id: int) -> int:
    """
    Deletes all user prompts that originate from a specific template ID.
    Returns the number of prompts deleted, or -1 on error.
    """
    log_prefix = f"[DB:UserPrompt:DeleteBySource:{source_template_id}]"
    sql = 'DELETE FROM user_prompts WHERE source_template_id = %s'
    cursor = get_cursor()
    deleted_count = 0
    try:
        cursor.execute(sql, (source_template_id,))
        deleted_count = cursor.rowcount
        get_db().commit()
        if deleted_count > 0:
            logging.info(f"{log_prefix} Deleted {deleted_count} user prompts linked to the source template.")
        else:
            logging.debug(f"{log_prefix} No user prompts found linked to the source template.")
        return deleted_count
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error deleting user prompts by source ID: {err}", exc_info=True)
        return -1 # Indicate error
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

# --- NEW: Functions for template synchronization ---

def get_user_synced_prompts_map(user_id: int) -> Dict[int, UserPrompt]:
    """
    Retrieves a user's prompts that originated from a template,
    and returns them as a dictionary mapped by their source_template_id.
    """
    log_prefix = f"[DB:UserPrompt:User:{user_id}]"
    sql = 'SELECT * FROM user_prompts WHERE user_id = %s AND source_template_id IS NOT NULL'
    prompts_map: Dict[int, UserPrompt] = {}
    cursor = get_cursor()
    try:
        cursor.execute(sql, (user_id,))
        rows = cursor.fetchall()
        for row in rows:
            prompt = _map_row_to_user_prompt(row)
            if prompt and prompt.source_template_id is not None:
                prompts_map[prompt.source_template_id] = prompt
        logging.debug(f"{log_prefix} Retrieved {len(prompts_map)} synced prompts map.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving synced prompts map: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return prompts_map

def update_synced_prompt(prompt_id: int, title: str, prompt_text: str, color: str) -> bool:
    """
    Updates a synced user prompt from a template. Does NOT break the source link.
    This is called by the sync service, not by direct user action.
    """
    log_prefix = f"[DB:UserPrompt:{prompt_id}]"
    now_utc_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    sql = '''
        UPDATE user_prompts
        SET title = %s, prompt_text = %s, color = %s, updated_at = %s
        WHERE id = %s
        '''
    cursor = get_cursor()
    try:
        cursor.execute(sql, (title, prompt_text, color, now_utc_iso, prompt_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logging.info(f"{log_prefix} Synced prompt updated from template.")
            return True
        return False # No rows affected, maybe data was identical
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error updating synced prompt: {err}", exc_info=True)
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def get_all_user_ids() -> List[int]:
    """Retrieves a list of all user IDs."""
    log_prefix = "[DB:User]"
    sql = 'SELECT id FROM users'
    user_ids = []
    cursor = get_cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        user_ids = [row['id'] for row in rows]
        logging.debug(f"{log_prefix} Retrieved {len(user_ids)} user IDs.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving all user IDs: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return user_ids