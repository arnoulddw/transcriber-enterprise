# app/models/transcription.py
# Defines functions for interacting with the 'transcriptions' database table using MySQL.
# Focuses on core job lifecycle management.

from app.logging_config import get_logger
import json
import os
from flask import current_app  # Used for init_db_command context
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

# Import MySQL specific error class
from mysql.connector import Error as MySQLError

# Import centralized DB functions (now MySQL based)
from app.database import get_db, get_cursor

def init_db_command() -> None:
    """
    Initializes the 'transcriptions' table schema in the MySQL database.
    Called via the 'flask init-db' command or initialization sequence.
    Ensures the table and indices exist.
    Includes columns for user association, file metadata, status, and results.
    Uses transactions for atomicity.
    """
    cursor = get_cursor()
    logger = get_logger(__name__, component="DB:Schema:MySQL")
    logger.info("Checking/Initializing 'transcriptions' table schema...")

    try:
        # --- Dependency Check: Ensure 'users' table exists first ---
        cursor.execute("SHOW TABLES LIKE 'users'")
        if not cursor.fetchone():
            logger.error("Cannot initialize 'transcriptions' table: 'users' table does not exist yet.")
            raise RuntimeError("User table must exist before transcriptions table can be initialized.")
        cursor.fetchall()  # Consume results if any

        # --- Create 'transcriptions' table if it doesn't exist (MySQL syntax) ---
        # --- MODIFIED: Added 'disabled' to title_generation_status ENUM ---
        create_table_sql = '''
            CREATE TABLE IF NOT EXISTS transcriptions (
                id VARCHAR(36) PRIMARY KEY,
                user_id INT NOT NULL,
                filename VARCHAR(255),
                generated_title VARCHAR(255) DEFAULT NULL,
                title_generation_status ENUM('pending', 'processing', 'success', 'failed', 'disabled') NOT NULL DEFAULT 'pending',
                file_size_mb DOUBLE,
                audio_length_minutes DOUBLE,
                detected_language VARCHAR(10),
                transcription_text MEDIUMTEXT,
                api_used VARCHAR(50),
                created_at TEXT NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                progress_log JSON,
                error_message TEXT,
                context_prompt_used BOOLEAN DEFAULT FALSE,
                downloaded BOOLEAN DEFAULT FALSE,
                is_hidden_from_user BOOLEAN NOT NULL DEFAULT FALSE,
                hidden_date DATETIME DEFAULT NULL,
                hidden_reason ENUM('USER_DELETED', 'RETENTION_POLICY') DEFAULT NULL,
                llm_operation_id INT DEFAULT NULL,
                llm_operation_status VARCHAR(20) DEFAULT NULL,
                llm_operation_result MEDIUMTEXT,
                llm_operation_error TEXT DEFAULT NULL,
                llm_operation_ran_at DATETIME DEFAULT NULL,
                pending_workflow_prompt_text TEXT DEFAULT NULL,
                pending_workflow_prompt_title VARCHAR(100) DEFAULT NULL,
                pending_workflow_prompt_color VARCHAR(7) DEFAULT NULL,
                pending_workflow_origin_prompt_id INT DEFAULT NULL,
                cost DECIMAL(10, 5) DEFAULT NULL,

                 FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                 INDEX idx_transcription_user (user_id),
                INDEX idx_transcription_status (status),
                INDEX idx_transcription_created_at (created_at(20)),
                INDEX idx_transcription_api_used (api_used),
                INDEX idx_transcription_language (detected_language),
                INDEX idx_transcription_user_hidden_created (user_id, is_hidden_from_user, created_at(20)),
                INDEX idx_transcription_hidden_date (is_hidden_from_user, hidden_date),
                INDEX idx_title_generation_status (title_generation_status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        '''
        # --- END MODIFIED ---
        cursor.execute(create_table_sql)
        logger.debug("CREATE TABLE IF NOT EXISTS transcriptions executed.")

        # --- Idempotent ALTER TABLE to handle potential existing tables ---
        # Check and rename/modify audio_length_seconds if it exists
        cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'audio_length_seconds'")
        old_col_exists = cursor.fetchone()
        cursor.fetchall()  # Consume remaining results
        if old_col_exists:
            logger.info("Found old 'audio_length_seconds' column. Renaming and changing type to DOUBLE for 'audio_length_minutes'.")
            cursor.execute("ALTER TABLE transcriptions CHANGE COLUMN audio_length_seconds audio_length_minutes DOUBLE")
        else:
            cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'audio_length_minutes'")
            new_col_exists = cursor.fetchone()
            cursor.fetchall()  # Consume remaining results
            if not new_col_exists:
                logger.info("Adding 'audio_length_minutes' column (DOUBLE).")
                cursor.execute("ALTER TABLE transcriptions ADD COLUMN audio_length_minutes DOUBLE AFTER file_size_mb")

        # Check and add context_prompt_used
        cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'context_prompt_used'")
        context_col_exists = cursor.fetchone()
        cursor.fetchall()  # Consume remaining results
        if not context_col_exists:
            logger.info("Adding 'context_prompt_used' column (BOOLEAN).")
            cursor.execute("ALTER TABLE transcriptions ADD COLUMN context_prompt_used BOOLEAN DEFAULT FALSE AFTER error_message")

        # Check and add downloaded
        cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'downloaded'")
        downloaded_col_exists = cursor.fetchone()
        cursor.fetchall()  # Consume remaining results
        if not downloaded_col_exists:
            logger.info("Adding 'downloaded' column (BOOLEAN).")
            cursor.execute("ALTER TABLE transcriptions ADD COLUMN downloaded BOOLEAN DEFAULT FALSE AFTER context_prompt_used")

        # Check and add is_hidden_from_user
        cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'is_hidden_from_user'")
        hidden_flag_exists = cursor.fetchone()
        cursor.fetchall()  # Consume remaining results
        if not hidden_flag_exists:
            logger.info("Adding 'is_hidden_from_user' column (BOOLEAN).")
            cursor.execute("ALTER TABLE transcriptions ADD COLUMN is_hidden_from_user BOOLEAN NOT NULL DEFAULT FALSE AFTER downloaded")

        # Check and add hidden_date
        cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'hidden_date'")
        hidden_date_exists = cursor.fetchone()
        cursor.fetchall()  # Consume remaining results
        if not hidden_date_exists:
            logger.info("Adding 'hidden_date' column (DATETIME).")
            cursor.execute("ALTER TABLE transcriptions ADD COLUMN hidden_date DATETIME DEFAULT NULL AFTER is_hidden_from_user")

        # Check and add hidden_reason
        cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'hidden_reason'")
        hidden_reason_exists = cursor.fetchone()
        cursor.fetchall()  # Consume remaining results
        if not hidden_reason_exists:
            logger.info("Adding 'hidden_reason' column (ENUM).")
            cursor.execute("ALTER TABLE transcriptions ADD COLUMN hidden_reason ENUM('USER_DELETED', 'RETENTION_POLICY') DEFAULT NULL AFTER hidden_date")

        # Check and add workflow columns
        cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'llm_operation_id'")
        workflow_col_exists = cursor.fetchone()
        cursor.fetchall()
        if not workflow_col_exists:
            logger.info("Adding workflow columns to 'transcriptions' table.")
            alter_workflow_sql = """
                  ALTER TABLE transcriptions
                  ADD COLUMN llm_operation_id INT DEFAULT NULL AFTER error_message,
                  ADD COLUMN llm_operation_status VARCHAR(20) DEFAULT NULL AFTER llm_operation_id,
                  ADD COLUMN llm_operation_result MEDIUMTEXT AFTER llm_operation_status,
                  ADD COLUMN llm_operation_error TEXT DEFAULT NULL AFTER llm_operation_result,
                  ADD COLUMN llm_operation_ran_at DATETIME DEFAULT NULL AFTER llm_operation_error
            """
            cursor.execute(alter_workflow_sql)

        # Add generated_title and title_generation_status columns idempotently
        cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'generated_title'")
        gen_title_exists = cursor.fetchone()
        cursor.fetchall()
        if not gen_title_exists:
            logger.info("Adding 'generated_title' column (VARCHAR(255)) to 'transcriptions' table.")
            cursor.execute("ALTER TABLE transcriptions ADD COLUMN generated_title VARCHAR(255) DEFAULT NULL AFTER filename")

        cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'title_generation_status'")
        title_status_exists = cursor.fetchone()
        cursor.fetchall()
        if not title_status_exists:
            logger.info("Adding 'title_generation_status' column (ENUM) to 'transcriptions' table.")
            # --- MODIFIED: Added 'disabled' to ENUM definition for new column ---
            cursor.execute("ALTER TABLE transcriptions ADD COLUMN title_generation_status ENUM('pending', 'processing', 'success', 'failed', 'disabled') NOT NULL DEFAULT 'pending' AFTER generated_title")
            # --- END MODIFIED ---
        else:
            # --- MODIFIED: Modify existing column to include 'disabled' ---
            cursor.execute("SELECT COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'transcriptions' AND COLUMN_NAME = 'title_generation_status'")
            current_enum_type = cursor.fetchone()['COLUMN_TYPE']
            cursor.fetchall()
            if 'disabled' not in current_enum_type:
                logger.info("Modifying 'title_generation_status' ENUM to include 'disabled'.")
                cursor.execute("ALTER TABLE transcriptions MODIFY COLUMN title_generation_status ENUM('pending', 'processing', 'success', 'failed', 'disabled') NOT NULL DEFAULT 'pending'")
            # --- END MODIFIED ---


        # --- MODIFIED: Add pending_workflow_origin_prompt_id column idempotently ---
        pending_workflow_columns = {
            'pending_workflow_prompt_text': "TEXT DEFAULT NULL AFTER llm_operation_ran_at",
            'pending_workflow_prompt_title': "VARCHAR(100) DEFAULT NULL AFTER pending_workflow_prompt_text",
            'pending_workflow_prompt_color': "VARCHAR(7) DEFAULT NULL AFTER pending_workflow_prompt_title",
            'pending_workflow_origin_prompt_id': "INT DEFAULT NULL AFTER pending_workflow_prompt_color" # Added
        }
        # --- END MODIFIED ---
        for col_name, col_def in pending_workflow_columns.items():
            cursor.execute(f"SHOW COLUMNS FROM transcriptions LIKE '{col_name}'")
            col_exists = cursor.fetchone()
            cursor.fetchall()
            if not col_exists:
                logger.info(f"Adding '{col_name}' column to 'transcriptions' table.")
                cursor.execute(f"ALTER TABLE transcriptions ADD COLUMN {col_name} {col_def}")
        # --- END NEW ---
 
        # Check and add cost
        cursor.execute("SHOW COLUMNS FROM transcriptions LIKE 'cost'")
        cost_col_exists = cursor.fetchone()
        cursor.fetchall()  # Consume remaining results
        if not cost_col_exists:
            logger.info("Adding 'cost' column (DECIMAL(10, 5)).")
            cursor.execute("ALTER TABLE transcriptions ADD COLUMN cost DECIMAL(10, 5) DEFAULT NULL AFTER pending_workflow_origin_prompt_id")

        # --- Add/Check Indexes ---
        index_checks = {
            'idx_transcription_created_at': 'created_at(20)',
            'idx_transcription_api_used': 'api_used',
            'idx_transcription_language': 'detected_language',
            'idx_transcription_user_hidden_created': 'user_id, is_hidden_from_user, created_at(20)',
            'idx_transcription_hidden_date': 'is_hidden_from_user, hidden_date',
            'idx_title_generation_status': 'title_generation_status'
        }
        for idx_name, col_def in index_checks.items():
            cursor.execute(f"SHOW INDEX FROM transcriptions WHERE Key_name = '{idx_name}'")
            idx_exists = cursor.fetchone()
            cursor.fetchall()
            if not idx_exists:
                logger.info(f"Adding index '{idx_name}' to 'transcriptions' table.")
                cursor.execute(f"ALTER TABLE transcriptions ADD INDEX {idx_name} ({col_def})")
        get_db().commit()
        logger.info("'transcriptions' table schema verified/initialized.")

    except MySQLError as err:
        logger.error(f"MySQL error during 'transcriptions' table initialization: {err}", exc_info=True)
        get_db().rollback()
        raise
    except RuntimeError as e:  # Catch dependency errors
        logger.error(f"Initialization dependency error: {e}")
        get_db().rollback()
        raise
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def _map_row_to_transcription_dict(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Maps a database row (dictionary) to a dictionary."""
    if not row:
        return None

    # Handle potential JSON decoding if progress_log is stored as TEXT
    if isinstance(row.get('progress_log'), str):
         try:
             row['progress_log'] = json.loads(row['progress_log'])
         except (json.JSONDecodeError, TypeError):
             get_logger(__name__).warning(f"Failed to decode progress_log JSON from TEXT field for job {row.get('id')}.")
             row['progress_log'] = ["Error decoding log."]  # Provide fallback

    # Ensure audio_length_minutes is float
    if 'audio_length_minutes' in row and row['audio_length_minutes'] is not None:
        try:
            row['audio_length_minutes'] = float(row['audio_length_minutes'])
        except (ValueError, TypeError):
            get_logger(__name__).warning(f"Could not convert audio_length_minutes '{row['audio_length_minutes']}' to float for job {row.get('id')}. Setting to 0.0.")
            row['audio_length_minutes'] = 0.0
    elif 'audio_length_minutes' not in row:
         row['audio_length_minutes'] = 0.0  # Default if column somehow missing after map

    # Ensure boolean fields are bool
    row['context_prompt_used'] = bool(row.get('context_prompt_used', False))
    row['downloaded'] = bool(row.get('downloaded', False))
    row['is_hidden_from_user'] = bool(row.get('is_hidden_from_user', False))

    # Convert datetime fields to string if they are datetime objects
    datetime_fields = ['hidden_date', 'llm_operation_ran_at']
    for field in datetime_fields:
        if isinstance(row.get(field), datetime):
            try:
                row[field] = row[field].replace(tzinfo=timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
            except Exception as e:
                get_logger(__name__).warning(f"Error formatting datetime field '{field}' for job {row.get('id')}: {e}")
                row[field] = str(row[field])

    row['generated_title'] = row.get('generated_title')
    row['title_generation_status'] = row.get('title_generation_status', 'pending')

    # --- MODIFIED: Ensure pending_workflow_origin_prompt_id is present ---
    row['pending_workflow_prompt_text'] = row.get('pending_workflow_prompt_text')
    row['pending_workflow_prompt_title'] = row.get('pending_workflow_prompt_title')
    row['pending_workflow_prompt_color'] = row.get('pending_workflow_prompt_color')
    row['pending_workflow_origin_prompt_id'] = row.get('pending_workflow_origin_prompt_id') # Added
    # --- END MODIFIED ---

    return row

# --- MODIFIED: Add pending_workflow_origin_prompt_id parameter ---
def create_transcription_job(job_id: str, user_id: int, filename: str, api_used: str,
                             file_size_mb: float, audio_length_minutes: float,
                             context_prompt_used: bool,
                             pending_workflow_prompt_text: Optional[str] = None,
                             pending_workflow_prompt_title: Optional[str] = None,
                             pending_workflow_prompt_color: Optional[str] = None,
                             pending_workflow_origin_prompt_id: Optional[int] = None
                             ) -> None:
# --- END MODIFIED ---
    """
    Creates an initial record for a transcription job in the database.
    Sets the status to 'pending'.
    Raises MySQLError on failure.
    """
    logger = get_logger(__name__, job_id=job_id, user_id=user_id, component="DB:Job")
    # --- MODIFIED: Added pending_workflow_origin_prompt_id to INSERT and logging ---
    sql = '''
        INSERT INTO transcriptions (
            id, user_id, filename, generated_title, title_generation_status,
            file_size_mb, audio_length_minutes, api_used,
            created_at, status, progress_log, error_message, context_prompt_used, downloaded,
            is_hidden_from_user, hidden_date, hidden_reason,
            llm_operation_id, llm_operation_status, llm_operation_result, llm_operation_error, llm_operation_ran_at,
            pending_workflow_prompt_text, pending_workflow_prompt_title, pending_workflow_prompt_color,
            pending_workflow_origin_prompt_id, cost
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
    # --- END MODIFIED ---
    initial_log_entry = f"Job created at {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}."
    initial_log_json = json.dumps([initial_log_entry])

    cursor = get_cursor()
    try:
        # --- MODIFIED: Added pending_workflow_origin_prompt_id to execute parameters ---
        cursor.execute(sql, (
            job_id, user_id, filename, None, 'pending',
            file_size_mb, audio_length_minutes, api_used,
            datetime.now(timezone.utc).isoformat(), 'pending', initial_log_json, None,
            context_prompt_used, False,
            False, None, None,
            None, None, None, None, None, # Workflow fields
            pending_workflow_prompt_text, pending_workflow_prompt_title, pending_workflow_prompt_color, # Existing pending workflow fields
            pending_workflow_origin_prompt_id, # New field
            None # cost
        ))
        # --- END MODIFIED ---
        get_db().commit()
        # --- MODIFIED: Updated log message ---
        pending_wf_log = "No"
        if pending_workflow_prompt_text or pending_workflow_origin_prompt_id:
            pending_wf_log = f"Yes (Text: {'Set' if pending_workflow_prompt_text else 'Not Set'}, ID: {pending_workflow_origin_prompt_id if pending_workflow_origin_prompt_id else 'Not Set'})"
        logger.debug(f"Created initial job record for '{filename}' (Size: {file_size_mb:.2f} MB, Length: {audio_length_minutes:.2f} min, Context: {context_prompt_used}, Pending WF: {pending_wf_log}).")
        # --- END MODIFIED ---
    except MySQLError as err:
        logger.error(f"Error creating job record: {err}", exc_info=True)
        get_db().rollback()
        raise  # Re-raise the exception
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def update_job_progress(job_id: str, message: str) -> None:
    """
    Appends a progress message to the job's progress log (JSON array/TEXT) in the database.
    Uses MySQL's JSON_ARRAY_APPEND if JSON type is used, otherwise reads/modifies/writes TEXT.
    """
    short_job_id = job_id[:8]
    log_prefix = f"[DB:Job:{short_job_id}]"
    cursor = get_cursor()

    is_json_type = False
    try:
        cursor.execute("SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'transcriptions' AND COLUMN_NAME = 'progress_log'")
        result = cursor.fetchone()
        cursor.fetchall()
        if result and result['DATA_TYPE'].lower() == 'json':
            is_json_type = True
    except MySQLError as schema_err:
        get_logger(__name__).warning(f"Could not determine progress_log column type for job {job_id}: {schema_err}. Assuming TEXT fallback.")
        is_json_type = False
    except Exception as e:
         get_logger(__name__).warning(f"Error checking progress_log column type for job {job_id}: {e}. Assuming TEXT fallback.")
         is_json_type = False

    try:
        if is_json_type:
            sql = """
                UPDATE transcriptions
                SET progress_log = JSON_ARRAY_APPEND(
                    COALESCE(progress_log, JSON_ARRAY()),
                    '$',
                    %s
                )
                WHERE id = %s
            """
            cursor.execute(sql, (message, job_id))
        else:
            cursor.execute("SELECT progress_log FROM transcriptions WHERE id = %s", (job_id,))
            row = cursor.fetchone()
            cursor.fetchall()

            if row:
                current_log_json = row['progress_log']
                current_log = []
                try:
                    if current_log_json:
                        parsed_log = json.loads(current_log_json)
                        if isinstance(parsed_log, list):
                            current_log = parsed_log
                        else:
                            get_logger(__name__).warning(f"Progress log TEXT is not a list ({type(parsed_log)}) for job {job_id}. Resetting.")
                except (json.JSONDecodeError, TypeError):
                    get_logger(__name__).warning(f"Could not parse progress log TEXT for job {job_id}. Resetting log. Content: {current_log_json}")
    
                current_log.append(message)
                new_log_json = json.dumps(current_log)
                cursor.execute("UPDATE transcriptions SET progress_log = %s WHERE id = %s", (new_log_json, job_id))
            else:
                 get_logger(__name__).warning(f"Attempted to update progress for non-existent job {job_id} (TEXT fallback).")

        get_db().commit()
        get_logger(__name__, job_id=job_id).debug(f"Appended progress message: '{message}'")

    except MySQLError as err:
        get_logger(__name__, job_id=job_id).error(f"MySQL error updating DB progress log: {err}", exc_info=True)
        try:
            get_db().rollback()
        except Exception as rb_err:
            get_logger(__name__, job_id=job_id).error(f"Error during rollback after progress update failure: {rb_err}")
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def update_job_status(job_id: str, status: str) -> None:
    """Updates the status field of a specific job record."""
    logger = get_logger(__name__, job_id=job_id, component="DB:Job")
    valid_statuses = ['pending', 'processing', 'finished', 'error', 'cancelling', 'cancelled']
    if status not in valid_statuses:
        logger.error(f"Attempted to set invalid status: '{status}'")
        return

    sql = "UPDATE transcriptions SET status = %s WHERE id = %s"
    cursor = get_cursor()
    try:
        cursor.execute(sql, (status, job_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.info(f"Updated status to: {status}")
        else:
            logger.warning("Attempted to update status for non-existent job.")
    except MySQLError as err:
        logger.error(f"Error updating status to '{status}': {err}", exc_info=True)
        get_db().rollback()
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def set_job_error(job_id: str, error_message: str) -> None:
    """
    Sets the job status to 'error' and records the error message.
    Also attempts to add the error message to the progress log.
    """
    logger = get_logger(__name__, job_id=job_id, component="DB:Job")

    try:
        update_job_progress(job_id, f"ERROR: {error_message}")
    except Exception as prog_err:
        logger.error(f"Failed to add error message to progress log: {prog_err}", exc_info=True)

    sql = "UPDATE transcriptions SET status = 'error', error_message = %s WHERE id = %s"
    cursor = get_cursor()
    try:
        cursor.execute(sql, (error_message, job_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.error(f"Set error status. Message: {error_message}")
        else:
             logger.warning("Attempted to set error status for non-existent job.")
    except MySQLError as err:
        logger.error(f"Error setting error status in DB: {err}", exc_info=True)
        get_db().rollback()
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def finalize_job_success(job_id: str, transcription_text: str, detected_language: str) -> None:
    """
    Updates a job record upon successful completion. Sets status to 'finished',
    saves the transcription text and detected language, and clears any previous error message.
    Also adds a success message to the progress log.
    """
    logger = get_logger(__name__, job_id=job_id, component="DB:Job")

    try:
        update_job_progress(job_id, "Transcription successful and saved.")
    except Exception as prog_err:
        logger.error(f"Failed to add success message to progress log: {prog_err}", exc_info=True)

    sql = """
        UPDATE transcriptions
        SET status = 'finished',
            transcription_text = %s,
            detected_language = %s,
            error_message = NULL
        WHERE id = %s
        """
    cursor = get_cursor()
    try:
        cursor.execute(sql, (transcription_text, detected_language, job_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.info("Finalized job successfully in DB.")
        else:
             logger.warning("Attempted to finalize non-existent job.")
    except MySQLError as err:
        logger.error(f"Error finalizing successful job in DB: {err}", exc_info=True)
        get_db().rollback()
        try:
            set_job_error(job_id, f"Failed to save final results: {err}")
        except Exception as inner_e:
            logger.error(f"CRITICAL: Failed to set error status after finalize failure: {inner_e}")
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def get_transcription_by_id(transcription_id: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves a specific transcription job record by its ID.
    If user_id is provided, it ensures the job belongs to that user.
    Returns the job data as a dictionary or None if not found or not owned.
    """
    logger = get_logger(__name__, job_id=transcription_id, user_id=user_id, component="DB:Job")
    sql = 'SELECT * FROM transcriptions WHERE id = %s'
    params: List[Any] = [transcription_id]

    if user_id is not None:
        sql += ' AND user_id = %s'
        params.append(user_id)

    cursor = get_cursor()
    transcription_dict = None
    try:
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone()
        cursor.fetchall()
        transcription_dict = _map_row_to_transcription_dict(row)

        if transcription_dict:
            log_msg = "Retrieved job record by ID."
            if user_id:
                log_msg += f" (Ownership verified for user {user_id})"
        else:
            log_msg = "Job record not found"
            if user_id:
                log_msg += f" or not owned by user {user_id}"
            logger.debug(log_msg)

    except MySQLError as err:
        log_msg = "Error retrieving transcription by ID"
        if user_id:
            log_msg += f" for user {user_id}"
        logger.error(f"{log_msg}: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return transcription_dict

def get_all_transcriptions(user_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Retrieves transcription records for a specific user, ordered by creation date DESC.
    Only retrieves records that are NOT hidden from the user.
    Optionally limits the number of records returned via the SQL query.
    """
    logger = get_logger(__name__, user_id=user_id, component="DB:History")
    sql = 'SELECT * FROM transcriptions WHERE user_id = %s AND is_hidden_from_user = FALSE ORDER BY created_at DESC'
    params: List[Any] = [user_id]

    if limit is not None and limit > 0:
        sql += ' LIMIT %s'
        params.append(limit)
        limit_msg = f" with limit {limit}"
    else:
        limit_msg = ""

    transcriptions = []
    cursor = get_cursor()
    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        transcriptions = [_map_row_to_transcription_dict(row) for row in rows if row]
        logger.debug(f"Retrieved {len(transcriptions)} visible transcription records{limit_msg}.")
    except MySQLError as err:
        logger.error(f"Error retrieving transcriptions: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return transcriptions

def delete_transcription(transcription_id: str, user_id: int) -> bool:
    """
    Soft-deletes a specific transcription record by ID, ensuring it belongs to the specified user.
    Sets the 'is_hidden_from_user' flag to TRUE and records the hidden date/reason.
    Returns True if the update was successful, False otherwise.
    """
    logger = get_logger(__name__, job_id=transcription_id, user_id=user_id, component="DB:Delete")
    sql = """
        UPDATE transcriptions
        SET is_hidden_from_user = TRUE,
            hidden_date = NOW(),
            hidden_reason = 'USER_DELETED'
        WHERE id = %s AND user_id = %s AND is_hidden_from_user = FALSE
        """
    cursor = get_cursor()
    try:
        cursor.execute(sql, (transcription_id, user_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.info("Soft-deleted transcription record owned by user.")
            return True
        else:
            cursor.execute('SELECT user_id, is_hidden_from_user FROM transcriptions WHERE id = %s', (transcription_id,))
            job_info = cursor.fetchone()
            cursor.fetchall()
            if not job_info:
                logger.warning("Soft delete failed: Transcription not found.")
            elif job_info['user_id'] != user_id:
                logger.warning("Soft delete failed due to ownership mismatch.")
            elif job_info['is_hidden_from_user']:
                logger.warning("Soft delete failed: Transcription already hidden.")
            else:
                logger.warning("Soft delete failed for an unknown reason (rowcount was 0).")
            return False
    except MySQLError as err:
        logger.error(f"Error soft-deleting transcription: {err}", exc_info=True)
        get_db().rollback()
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def restore_transcription(transcription_id: str, user_id: int) -> bool:
    """
    Restores a previously soft-deleted transcription by resetting the hidden flags.
    Returns True when the record was restored, False otherwise.
    """
    logger = get_logger(__name__, job_id=transcription_id, user_id=user_id, component="DB:Restore")
    sql = """
        UPDATE transcriptions
        SET is_hidden_from_user = FALSE,
            hidden_date = NULL,
            hidden_reason = NULL
        WHERE id = %s AND user_id = %s AND is_hidden_from_user = TRUE
        """
    cursor = get_cursor()
    try:
        cursor.execute(sql, (transcription_id, user_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.info("Restored soft-deleted transcription record for user.")
            return True
        logger.warning("Restore failed: transcription not found, not owned, or already visible.")
        return False
    except MySQLError as err:
        logger.error(f"Error restoring transcription: {err}", exc_info=True)
        get_db().rollback()
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def clear_transcriptions(user_id: int) -> int:
    """
    Soft-deletes ALL visible transcription records for a specific user.
    Sets the 'is_hidden_from_user' flag to TRUE and records the hidden date/reason.
    Returns the number of records hidden.
    """
    logger = get_logger(__name__, user_id=user_id, component="DB:Clear")
    sql = """
        UPDATE transcriptions
        SET is_hidden_from_user = TRUE,
            hidden_date = NOW(),
            hidden_reason = 'USER_DELETED'
        WHERE user_id = %s AND is_hidden_from_user = FALSE
        """
    hidden_count = 0
    cursor = get_cursor()
    try:
        cursor.execute(sql, (user_id,))
        hidden_count = cursor.rowcount
        get_db().commit()
        logger.info(f"Soft-deleted {hidden_count} transcription records.")
    except MySQLError as err:
        logger.error(f"Error clearing transcriptions: {err}", exc_info=True)
        get_db().rollback()
        hidden_count = 0
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return hidden_count

def mark_transcription_as_downloaded(transcription_id: str, user_id: int) -> bool:
    """Sets the 'downloaded' flag to TRUE for a specific job owned by the user."""
    logger = get_logger(__name__, job_id=transcription_id, user_id=user_id, component="DB:DownloadLog")
    sql = "UPDATE transcriptions SET downloaded = TRUE WHERE id = %s AND user_id = %s AND status = 'finished'"
    cursor = get_cursor()
    try:
        cursor.execute(sql, (transcription_id, user_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.info("Marked transcription as downloaded.")
            return True
        else:
            cursor.execute("SELECT status FROM transcriptions WHERE id = %s AND user_id = %s", (transcription_id, user_id))
            job_status = cursor.fetchone()
            cursor.fetchall()
            if job_status:
                logger.warning(f"Could not mark as downloaded. Job status is '{job_status['status']}'.")
            else:
                logger.warning("Could not mark as downloaded. Job not found or not owned by user.")
            return False
    except MySQLError as err:
        logger.error(f"Error marking transcription as downloaded: {err}", exc_info=True)
        get_db().rollback()
        return False
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def update_title_generation_status(transcription_id: str, status: str) -> bool:
    """Updates the title_generation_status for a specific transcription."""
    logger = get_logger(__name__, job_id=transcription_id, component="DB:TitleGen")
    # --- MODIFIED: Add 'disabled' to valid_statuses ---
    valid_statuses = ['pending', 'processing', 'success', 'failed', 'disabled']
    # --- END MODIFIED ---
    if status not in valid_statuses:
        logger.error(f"Attempted to set invalid title generation status: '{status}'")
        return False

    sql = "UPDATE transcriptions SET title_generation_status = %s WHERE id = %s"
    cursor = get_cursor()
    success = False
    try:
        cursor.execute(sql, (status, transcription_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.info(f"Updated title generation status to: {status}")
            success = True
        else:
            logger.warning("Attempted to update title generation status for non-existent job.")
    except MySQLError as err:
        logger.error(f"Error updating title generation status to '{status}': {err}", exc_info=True)
        get_db().rollback()
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return success

def update_transcription_cost(transcription_id: str, cost: float) -> bool:
    """Updates the cost for a specific transcription."""
    logger = get_logger(__name__, job_id=transcription_id, component="DB:Cost")
    sql = "UPDATE transcriptions SET cost = %s WHERE id = %s"
    cursor = get_cursor()
    success = False
    try:
        cursor.execute(sql, (cost, transcription_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.debug(f"Updated transcription cost to: {cost}")
            success = True
        else:
            logger.warning("Attempted to update cost for non-existent transcription.")
    except MySQLError as err:
        logger.error(f"Error updating transcription cost to '{cost}': {err}", exc_info=True)
        get_db().rollback()
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return success

def set_generated_title(transcription_id: str, title: str) -> bool:
    """Sets the generated_title and updates status to 'success'."""
    logger = get_logger(__name__, job_id=transcription_id, component="DB:TitleGen")
    sql = "UPDATE transcriptions SET generated_title = %s, title_generation_status = 'success' WHERE id = %s"
    cursor = get_cursor()
    success = False
    try:
        cursor.execute(sql, (title, transcription_id))
        get_db().commit()
        if cursor.rowcount > 0:
            logger.info(f"Set generated title and status to 'success'. Title: '{title}'")
            success = True
        else:
            logger.warning("Attempted to set generated title for non-existent job.")
    except MySQLError as err:
        logger.error(f"Error setting generated title: {err}", exc_info=True)
        get_db().rollback()
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return success
