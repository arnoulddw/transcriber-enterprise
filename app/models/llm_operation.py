# app/models/llm_operation.py
# Defines the LLMOperation model and database interaction functions for MySQL.

import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

# Import MySQL specific error class
from mysql.connector import Error as MySQLError

# Import centralized DB functions
from app.database import get_db, get_cursor

# Import config for provider validation
from app.config import Config
from app.core.utils import format_currency

# --- LLMOperation Class Definition (Optional but good practice) ---
class LLMOperation:
    id: int
    user_id: int
    provider: str
    operation_type: str
    input_text: Optional[str]
    result: Optional[str]
    transcription_id: Optional[str]  # Nullable foreign key to Transcription ID (VARCHAR 36)
    prompt_id: Optional[int]  # Nullable foreign key to UserPrompt or TemplatePrompt (or other prompt types)
    created_at: str
    completed_at: Optional[str]
    status: str  # e.g., 'pending', 'processing', 'finished', 'error'
    error: Optional[str]
    # Add other fields as needed, e.g., token counts, cost, model used

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.user_id = kwargs.get('user_id')
        self.provider = kwargs.get('provider')
        self.operation_type = kwargs.get('operation_type')
        self.input_text = kwargs.get('input_text')
        self.result = kwargs.get('result')
        self.transcription_id = kwargs.get('transcription_id')
        self.prompt_id = kwargs.get('prompt_id')
        self.created_at = kwargs.get('created_at')
        self.completed_at = kwargs.get('completed_at')
        self.status = kwargs.get('status', 'pending')
        self.error = kwargs.get('error')

    def __repr__(self):
        transcription_info = f", TranscriptionID:{self.transcription_id[:8]}..." if self.transcription_id else ""
        prompt_info = f", PromptID:{self.prompt_id}" if self.prompt_id else ""
        return f'<LLMOperation {self.id} (User:{self.user_id}, Provider:{self.provider}, Type:{self.operation_type}, Status:{self.status}{transcription_info}{prompt_info})>'

# --- Database Schema Initialization ---

def init_db_command() -> None:
    """Initializes the 'llm_operations' table schema."""
    cursor = get_cursor()
    log_prefix = "[DB:Schema:MySQL]"
    logging.info(f"{log_prefix} Checking/Initializing 'llm_operations' table...")
    try:
        # Dependency Checks
        cursor.execute("SHOW TABLES LIKE 'users'")
        if not cursor.fetchone():
            raise RuntimeError("User table must exist before llm_operations table can be initialized.")
        cursor.fetchall()
        cursor.execute("SHOW TABLES LIKE 'transcriptions'")
        if not cursor.fetchone():
            raise RuntimeError("Transcriptions table must exist before llm_operations table can be initialized.")
        cursor.fetchall()
        # Note: We don't strictly depend on prompt tables, as prompt_id is nullable

        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS llm_operations (
                id INT PRIMARY KEY AUTO_INCREMENT,
                user_id INT NOT NULL,
                provider VARCHAR(50) NOT NULL,
                operation_type VARCHAR(50) NOT NULL,
                input_text MEDIUMTEXT,
                result MEDIUMTEXT,
                transcription_id VARCHAR(36) DEFAULT NULL,
                prompt_id INT DEFAULT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT DEFAULT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                error TEXT DEFAULT NULL,
                cost DECIMAL(10, 5) DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (transcription_id) REFERENCES transcriptions (id) ON DELETE SET NULL,
                INDEX idx_llm_op_user (user_id),
                INDEX idx_llm_op_provider (provider),
                INDEX idx_llm_op_type (operation_type),
                INDEX idx_llm_op_status (status),
                INDEX idx_llm_op_transcription (transcription_id),
                INDEX idx_llm_op_prompt (prompt_id),
                INDEX idx_llm_op_created_at (created_at(20))
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            '''
        )
        get_db().commit()
        logging.info(f"{log_prefix} 'llm_operations' table schema verified/initialized.")

        # Check and add cost
        cursor.execute("SHOW COLUMNS FROM llm_operations LIKE 'cost'")
        cost_col_exists = cursor.fetchone()
        cursor.fetchall()  # Consume remaining results
        if not cost_col_exists:
            logging.info(f"{log_prefix} Adding 'cost' column (DECIMAL(10, 5)) to 'llm_operations' table.")
            cursor.execute("ALTER TABLE llm_operations ADD COLUMN cost DECIMAL(10, 5) DEFAULT NULL AFTER error")
        get_db().commit()
    except MySQLError as err:
        logging.error(f"{log_prefix} Error during 'llm_operations' table initialization: {err}", exc_info=True)
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

def _map_row_to_llm_operation_dict(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Maps a database row (dictionary) to a dictionary representing an LLMOperation."""
    if not row:
        return None
    return row

# --- CRUD Operations ---

def create_llm_operation(
    user_id: int,
    provider: str,
    operation_type: str,
    input_text: Optional[str] = None,
    transcription_id: Optional[str] = None,
    prompt_id: Optional[int] = None,
    status: str = 'pending'
) -> Optional[int]:
    """
    Creates an initial record for an LLM operation.

    Returns:
        The ID of the newly created operation, or None on failure.
    """
    log_prefix = f"[DB:LLMOperation:User:{user_id}]"

    if not any(provider.startswith(p) for p in Config.LLM_PROVIDERS):
        logging.error(f"{log_prefix} Invalid LLM provider specified: '{provider}'. Valid providers are: {Config.LLM_PROVIDERS}")
        return None

    sql = """
        INSERT INTO llm_operations (
            user_id, provider, operation_type, input_text, transcription_id,
            prompt_id, created_at, status
        ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
    """
    cursor = get_cursor()
    operation_id = None
    try:
        cursor.execute(sql, (
            user_id, provider, operation_type, input_text, transcription_id,
            prompt_id, status
        ))
        get_db().commit()
        operation_id = cursor.lastrowid
        logging.info(f"{log_prefix} Created LLM operation record ID {operation_id} (Type: {operation_type}, Provider: {provider}, Status: {status}).")
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error creating LLM operation record: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return operation_id

def update_llm_operation_status(
    operation_id: int,
    status: str,
    result: Optional[str] = None,
    error: Optional[str] = None
) -> bool:
    """Updates the status, result, error, and completed_at timestamp for an LLM operation."""
    log_prefix = f"[DB:LLMOperation:{operation_id}]"
    now_utc_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    valid_statuses = ['pending', 'processing', 'finished', 'error']
    if status not in valid_statuses:
        logging.error(f"{log_prefix} Attempted to set invalid status: '{status}'")
        return False

    update_fields = {'status': status}
    params = [status]

    if status in ['finished', 'error']:
        update_fields['completed_at'] = now_utc_iso
        params.append(now_utc_iso)

    if status == 'finished':
        update_fields['result'] = result
        update_fields['error'] = None
        params.append(result)
        params.append(None)
    elif status == 'error':
        update_fields['error'] = error
        params.append(error)
    elif status == 'processing':
        update_fields['completed_at'] = None
        params.append(None)

    set_clauses = ", ".join([f"{field} = %s" for field in update_fields])
    sql = f"UPDATE llm_operations SET {set_clauses} WHERE id = %s"
    params.append(operation_id)

    cursor = get_cursor()
    success = False
    try:
        cursor.execute(sql, tuple(params))
        get_db().commit()
        if cursor.rowcount > 0:
            logging.info(f"{log_prefix} Updated LLM operation status to '{status}'.")
            success = True
        else:
            logging.warning(f"{log_prefix} Update failed: LLM operation ID {operation_id} not found or no changes made.")
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error updating LLM operation status: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return success

def update_llm_operation_result(operation_id: int, user_id: int, new_result: str) -> bool:
    """
    Updates the result field of a specific LLM operation, verifying ownership.

    Args:
        operation_id: The ID of the LLM operation to update.
        user_id: The ID of the user attempting the update.
        new_result: The new result text.

    Returns:
        True if the update was successful (record found and owned) or if the new result matches the current value, False otherwise.
    """
    log_prefix = f"[DB:LLMOperation:{operation_id}:User:{user_id}]"
    sql = "UPDATE llm_operations SET result = %s WHERE id = %s AND user_id = %s"
    cursor = get_cursor()
    success = False
    try:
        cursor.execute(sql, (new_result, operation_id, user_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logging.info(f"{log_prefix} Updated LLM operation result.")
            success = True
        else:
            # Check if the record exists and if its result already equals the new value.
            cursor.execute("SELECT result, user_id FROM llm_operations WHERE id = %s", (operation_id,))
            op_info = cursor.fetchone()
            if not op_info:
                logging.warning(f"{log_prefix} Update result failed: LLM operation not found.")
            elif op_info['user_id'] != user_id:
                logging.warning(f"{log_prefix} Update result failed: Ownership mismatch.")
            elif op_info['result'] == new_result:
                logging.info(f"{log_prefix} Update result not needed: new result matches existing result.")
                success = True
            else:
                logging.warning(f"{log_prefix} Update result failed: No changes made (rowcount 0).")
    except MySQLError as err:
        get_db().rollback()
        logging.error(f"{log_prefix} Error updating LLM operation result: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return success

def get_llm_operation_by_id(operation_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves a specific LLM operation by its ID.
    Optionally verifies ownership if user_id is provided.
    """
    log_prefix = f"[DB:LLMOperation:{operation_id}]"
    sql = "SELECT * FROM llm_operations WHERE id = %s"
    params: List[Any] = [operation_id]

    if user_id is not None:
        sql += " AND user_id = %s"
        params.append(user_id)
        log_prefix += f":User:{user_id}"

    operation_dict = None
    cursor = get_cursor()
    try:
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone()
        operation_dict = _map_row_to_llm_operation_dict(row)
        if operation_dict:
            logging.debug(f"{log_prefix} Retrieved LLM operation record.")
        else:
            logging.debug(f"{log_prefix} LLM operation record not found or ownership mismatch.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving LLM operation: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return operation_dict
 
def update_llm_operation_cost(operation_id: int, cost: float) -> bool:
    """Updates the cost for a specific LLM operation."""
    log_prefix = f"[DB:Cost:LLMOp:{operation_id}]"
    sql = "UPDATE llm_operations SET cost = %s WHERE id = %s"
    cursor = get_cursor()
    success = False
    try:
        cursor.execute(sql, (cost, operation_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logging.info(f"{log_prefix} Updated LLM operation cost to: {format_currency(cost)}")
            success = True
        else:
            logging.warning(f"{log_prefix} Attempted to update cost for non-existent LLM operation.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error updating LLM operation cost to '{cost}': {err}", exc_info=True)
        get_db().rollback()
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return success

 # Add other necessary functions later (e.g., get_operations_by_user, get_operations_by_transcription)