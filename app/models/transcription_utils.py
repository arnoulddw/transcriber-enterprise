# app/models/transcription_utils.py
# Contains utility functions for transcription data, including analytics, stats, and purging.

import logging
import math 
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

# Import MySQL specific error class
from mysql.connector import Error as MySQLError

# Import centralized DB functions (now MySQL based)
from app.database import get_db, get_cursor

# Import the helper function from the main transcription model file
from .transcription import _map_row_to_transcription_dict

# Define a set of actual database column names that can be filtered on.
# These are the columns in the 'transcriptions' table.
VALID_TRANSCRIPTION_COLUMNS_FOR_FILTERING = {
    'id', 'user_id', 'filename', 'generated_title', 'title_generation_status',
    'file_size_mb', 'audio_length_minutes', 'detected_language',
    'transcription_text', 'api_used', 'created_at', 'status',
    'progress_log', 'error_message', 'context_prompt_used', 'downloaded',
    'is_hidden_from_user', 'hidden_date', 'hidden_reason',
    'llm_operation_id', 
    # --- MODIFIED: Added llm_operation_status ---
    'llm_operation_status', 
    # --- END MODIFIED ---
    'llm_operation_result',
    'llm_operation_error', 'llm_operation_ran_at',
    'pending_workflow_prompt_text', 'pending_workflow_prompt_title',
    'pending_workflow_prompt_color', 'cost'
}
 
 # --- Data Retrieval (Admin/Stats Focused) ---
def get_all_transcriptions_for_admin(user_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Retrieves ALL transcription records for a specific user (including hidden),
    ordered by creation date DESC. Intended for admin views.
    Optionally limits the number of records returned via the SQL query.
    """
    log_prefix = f"[DB:History:AdminView:User:{user_id}]"
    sql = 'SELECT * FROM transcriptions WHERE user_id = %s ORDER BY created_at DESC'
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
        logging.debug(f"{log_prefix} Retrieved {len(transcriptions)} total transcription records (including hidden){limit_msg}.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving all transcriptions for admin: {err}", exc_info=True)
        transcriptions = []
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return transcriptions

# --- User Stats Functions ---
def count_user_transcriptions(user_id: int) -> int:
    """Counts the total number of transcription records for a user (including hidden)."""
    log_prefix = f"[DB:Stats:User:{user_id}]"
    sql = 'SELECT COUNT(*) as count FROM transcriptions WHERE user_id = %s'
    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql, (user_id,))
        result = cursor.fetchone()
        cursor.fetchall() # Consume remaining results
        count = result['count'] if result else 0
        logging.debug(f"{log_prefix} Counted {count} total transcriptions (including hidden).")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error counting transcriptions: {err}", exc_info=True)
        count = 0
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count

def count_user_errors(user_id: int) -> int:
    """Counts the number of transcription records with status 'error' for a user (including hidden)."""
    log_prefix = f"[DB:Stats:User:{user_id}]"
    sql = "SELECT COUNT(*) as count FROM transcriptions WHERE user_id = %s AND status = 'error'"
    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql, (user_id,))
        result = cursor.fetchone()
        cursor.fetchall() # Consume remaining results
        count = result['count'] if result else 0
        logging.debug(f"{log_prefix} Counted {count} errored transcriptions (including hidden).")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error counting errors: {err}", exc_info=True)
        count = 0
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count

def get_total_audio_length_in_minutes(user_id: int) -> float:
    """
    Calculates the sum of 'audio_length_minutes' for all transcription records
    belonging to a specific user where the length is not NULL (including hidden).
    Returns the total duration in minutes as a float.
    """
    log_prefix = f"[DB:Stats:User:{user_id}]"
    sql = "SELECT SUM(audio_length_minutes) as total_minutes FROM transcriptions WHERE user_id = %s AND audio_length_minutes IS NOT NULL"
    cursor = get_cursor()
    total_minutes = 0.0
    try:
        cursor.execute(sql, (user_id,))
        result = cursor.fetchone()
        cursor.fetchall() # Consume remaining results
        total_minutes = result['total_minutes'] if result and result['total_minutes'] is not None else 0.0
        logging.debug(f"{log_prefix} Calculated total audio length (including hidden): {total_minutes:.2f} minutes")
        return float(total_minutes)
    except MySQLError as err:
        logging.error(f"{log_prefix} Error calculating total audio length in minutes: {err}", exc_info=True)
        total_minutes = 0.0
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return total_minutes

# --- History Purging Functions ---
def purge_user_history(user_id: int, max_items: int, retention_days: int) -> int:
    """
    Soft-deletes old and excess transcription history items for a specific user based on role limits.
    Applies retention days first, then max items limit. Only affects currently visible records.
    Uses a transaction for atomicity.
    Returns the total number of records hidden, or -1 on error.
    """
    if max_items <= 0 and retention_days <= 0:
        logging.debug(f"[DB:HistoryPurge:User:{user_id}] No history limits set. Skipping purge.")
        return 0

    cursor = get_cursor()
    hidden_count = 0
    log_prefix = f"[DB:HistoryPurge:User:{user_id}]"
    logging.debug(f"{log_prefix} Starting history purge (soft delete). Limits - MaxItems: {max_items}, RetentionDays: {retention_days}.")

    try:
        # 1. Hide by retention days
        if retention_days > 0:
            try:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
                cutoff_iso = cutoff_date.isoformat(timespec='seconds')
                logging.debug(f"{log_prefix} Hiding records older than {cutoff_iso} ({retention_days} days).")
                sql_hide_by_date = """
                    UPDATE transcriptions
                    SET is_hidden_from_user = TRUE, hidden_date = NOW(), hidden_reason = 'RETENTION_POLICY'
                    WHERE user_id = %s AND created_at < %s AND is_hidden_from_user = FALSE
                """
                cursor.execute(sql_hide_by_date, (user_id, cutoff_iso))
                hidden_by_date = cursor.rowcount
                if hidden_by_date > 0:
                    hidden_count += hidden_by_date
                    logging.debug(f"{log_prefix} Hid {hidden_by_date} records based on retention days.")
                else:
                    logging.debug(f"{log_prefix} No visible records found older than retention period.")
            except Exception as date_purge_err:
                 logging.error(f"{log_prefix} Error during date-based hiding step: {date_purge_err}", exc_info=True)

        # 2. Hide by max items
        if max_items > 0:
            try:
                cursor.execute("SELECT COUNT(*) FROM transcriptions WHERE user_id = %s AND is_hidden_from_user = FALSE", (user_id,))
                current_count_result = cursor.fetchone()
                cursor.fetchall()
                current_visible_count = current_count_result['count'] if current_count_result else 0
                logging.debug(f"{log_prefix} Current visible item count after date purge: {current_visible_count}. Max items limit: {max_items}.")

                if current_visible_count > max_items:
                    num_to_hide = current_visible_count - max_items
                    logging.debug(f"{log_prefix} Exceeds max items limit. Need to hide oldest {num_to_hide} visible records.")
                    sql_hide_by_count = """
                        UPDATE transcriptions
                        SET is_hidden_from_user = TRUE, hidden_date = NOW(), hidden_reason = 'RETENTION_POLICY'
                        WHERE user_id = %s AND is_hidden_from_user = FALSE
                        ORDER BY created_at ASC
                        LIMIT %s
                    """
                    cursor.execute(sql_hide_by_count, (user_id, num_to_hide))
                    hidden_by_count = cursor.rowcount
                    if hidden_by_count > 0:
                        hidden_count += hidden_by_count
                        logging.debug(f"{log_prefix} Hid {hidden_by_count} additional records based on max items limit.")
                    if hidden_by_count != num_to_hide:
                         logging.warning(f"{log_prefix} Mismatch hiding by count: Expected {num_to_hide}, Hid {hidden_by_count}.")
                else:
                     logging.debug(f"{log_prefix} Visible item count is within the max items limit.")
            except Exception as count_purge_err:
                 logging.error(f"{log_prefix} Error during count-based hiding step: {count_purge_err}", exc_info=True)

        get_db().commit()
        if hidden_count > 0:
            logging.debug(f"{log_prefix} History purge (soft delete) completed. Total hidden: {hidden_count}.")
        else:
            logging.debug(f"{log_prefix} History purge (soft delete) completed. No records hidden.")

    except MySQLError as err:
        logging.error(f"{log_prefix} MySQL error during history purge transaction: {err}", exc_info=True)
        try: get_db().rollback()
        except Exception as rb_err: logging.error(f"{log_prefix} Error during rollback after purge failure: {rb_err}")
        hidden_count = -1
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return hidden_count

def physically_delete_hidden_records(retention_period_days: int) -> int:
    """
    Physically deletes transcription records that have been hidden for longer
    than the specified retention period.
    Returns the number of records deleted, or -1 on error.
    """
    log_prefix = f"[DB:PhysicalDelete]"
    if retention_period_days <= 0:
        logging.warning(f"{log_prefix} Physical deletion period is zero or negative ({retention_period_days} days). Skipping physical deletion.")
        return 0

    cursor = get_cursor()
    deleted_count = 0
    logging.debug(f"{log_prefix} Starting physical deletion of records hidden for more than {retention_period_days} days.")

    try:
        sql = """
            DELETE FROM transcriptions
            WHERE is_hidden_from_user = TRUE
              AND hidden_date < (NOW() - INTERVAL %s DAY)
        """
        cursor.execute(sql, (retention_period_days,))
        deleted_count = cursor.rowcount
        get_db().commit()
        if deleted_count > 0:
            logging.debug(f"{log_prefix} Physically deleted {deleted_count} hidden records.")
        else:
            logging.debug(f"{log_prefix} No hidden records found older than {retention_period_days} days.")

    except MySQLError as err:
        logging.error(f"{log_prefix} MySQL error during physical deletion: {err}", exc_info=True)
        try: get_db().rollback()
        except Exception as rb_err: logging.error(f"{log_prefix} Error during rollback after physical deletion failure: {rb_err}")
        deleted_count = -1
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return deleted_count

# --- Admin Analytics Functions ---
def count_transcriptions_since(cutoff_datetime: datetime) -> int:
    """Counts transcriptions created since a specific datetime (including hidden)."""
    sql = "SELECT COUNT(*) as count FROM transcriptions WHERE created_at >= %s"
    cutoff_iso = cutoff_datetime.isoformat(timespec='seconds')
    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql, (cutoff_iso,))
        result = cursor.fetchone()
        cursor.fetchall()
        count = result['count'] if result else 0
        logging.debug(f"[DB:Admin] Counted {count} transcriptions since {cutoff_iso} (including hidden).")
    except MySQLError as err:
        logging.error(f"[DB:Admin] Error counting transcriptions since {cutoff_iso}: {err}", exc_info=True)
        count = 0
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count

def count_errors_since(cutoff_datetime: datetime) -> int:
    """Counts transcriptions with status 'error' created since a specific datetime (including hidden)."""
    sql = "SELECT COUNT(*) as count FROM transcriptions WHERE status = 'error' AND created_at >= %s"
    cutoff_iso = cutoff_datetime.isoformat(timespec='seconds')
    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql, (cutoff_iso,))
        result = cursor.fetchone()
        cursor.fetchall()
        count = result['count'] if result else 0
        logging.debug(f"[DB:Admin] Counted {count} errors since {cutoff_iso} (including hidden).")
    except MySQLError as err:
        logging.error(f"[DB:Admin] Error counting errors since {cutoff_iso}: {err}", exc_info=True)
        count = 0
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count

def _build_filter_sql_and_params(base_sql: str, start_dt: Optional[datetime], end_dt: Optional[datetime], **filters) -> Tuple[str, List[Any]]:
    """Helper to build SQL WHERE clauses and parameters for filtering."""
    sql = base_sql
    params = []

    if start_dt:
        sql += " AND created_at >= %s"
        params.append(start_dt.isoformat(timespec='seconds'))
    if end_dt:
        sql += " AND created_at < %s"
        params.append(end_dt.isoformat(timespec='seconds'))

    column_mapping = {
        'workflow_status': 'llm_operation_status',
        # Add other direct mappings if needed, e.g. 'workflow_model_used': 'actual_column_for_model'
        # For now, 'workflow_model_used' is not directly filterable on 'transcriptions' table by this generic function.
    }

    for key, value in filters.items():
        if value is None:  # Skip filters with None value
            continue

        actual_column_name = key
        operator = "="
        is_list_filter = False

        # Handle special suffixed keys for IN, NOT IN, NE (Not Equal)
        if key.endswith('__in') and isinstance(value, (list, tuple)):
            actual_column_name = key[:-4]  # e.g., status__in -> status
            operator = "IN"
            is_list_filter = True
            if not value: continue  # Skip empty IN lists
        elif key.endswith('__not_in') and isinstance(value, (list, tuple)):
            actual_column_name = key[:-8] # e.g., status__not_in -> status
            operator = "NOT IN"
            is_list_filter = True
            if not value: continue  # Skip empty NOT IN lists
        elif key.endswith('__ne') and not isinstance(value, (list, tuple)):
            actual_column_name = key[:-4] # e.g., status__ne -> status
            operator = "!="
        
        # Apply mapping if the original key (before suffix removal) is in column_mapping
        if key in column_mapping: # Check original key for mapping
            actual_column_name = column_mapping[key]
        elif actual_column_name in column_mapping: # Check suffix-stripped key for mapping
             actual_column_name = column_mapping[actual_column_name]


        if actual_column_name in VALID_TRANSCRIPTION_COLUMNS_FOR_FILTERING:
            if is_list_filter:
                placeholders = ', '.join(['%s'] * len(value))
                sql += f" AND {actual_column_name} {operator} ({placeholders})"
                params.extend(list(value))
            else:
                sql += f" AND {actual_column_name} {operator} %s"
                params.append(value)
        else:
            logging.warning(f"[DB:AdminUtils] Ignored invalid or unmapped filter key: '{key}' (resolved to '{actual_column_name}')")
            
    return sql, params


def count_jobs_in_range(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None, **filters) -> int:
    """
    Counts transcription jobs within a date range, optionally applying filters (includes hidden).
    Supports equality filters and suffixed filters like 'status__in', 'status__not_in', 'status__ne'.
    Maps 'workflow_status' to 'llm_operation_status' for DB query.
    """
    base_sql = "SELECT COUNT(*) as count FROM transcriptions WHERE 1=1"
    sql, params = _build_filter_sql_and_params(base_sql, start_dt, end_dt, **filters)
    
    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql, tuple(params))
        result = cursor.fetchone()
        cursor.fetchall()
        count = result['count'] if result else 0
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] Error counting jobs in range ({start_dt} - {end_dt}) with filters {filters}: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count

def sum_minutes_in_range(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None, **filters) -> float:
    """
    Sums audio_length_minutes within a date range, optionally applying filters (includes hidden).
    Supports equality filters and suffixed filters like 'status__in', 'status__not_in', 'status__ne'.
    Maps 'workflow_status' to 'llm_operation_status' for DB query.
    """
    base_sql = "SELECT SUM(audio_length_minutes) as total_minutes FROM transcriptions WHERE audio_length_minutes IS NOT NULL"
    sql, params = _build_filter_sql_and_params(base_sql, start_dt, end_dt, **filters)

    cursor = get_cursor()
    total_minutes = 0.0
    try:
        cursor.execute(sql, tuple(params))
        result = cursor.fetchone()
        cursor.fetchall()
        total_minutes = result['total_minutes'] if result and result['total_minutes'] is not None else 0.0
        return float(total_minutes)
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] Error summing minutes in range ({start_dt} - {end_dt}) with filters {filters}: {err}", exc_info=True)
        return 0.0
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def get_api_distribution_in_range(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None, aggregate_minutes: bool = False, **filters) -> Dict[str, float]:
    """
    Gets job counts or summed minutes per API used within a date range (includes hidden).
    Supports additional filters.
    """
    aggregate_column = "SUM(audio_length_minutes)" if aggregate_minutes else "COUNT(*)"
    result_column_name = "total_value"
    
    base_sql = f"SELECT api_used, {aggregate_column} as {result_column_name} FROM transcriptions WHERE 1=1"
    if aggregate_minutes:
        base_sql += " AND audio_length_minutes IS NOT NULL"
        
    sql, params = _build_filter_sql_and_params(base_sql, start_dt, end_dt, **filters)
    sql += " GROUP BY api_used"

    cursor = get_cursor()
    distribution = {}
    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        for row in rows:
            api = row['api_used'] or 'Unknown'
            value = row[result_column_name]
            distribution[api] = float(value) if aggregate_minutes and value is not None else int(value) if value is not None else 0
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] Error getting API {'minute' if aggregate_minutes else 'job'} distribution with filters {filters}: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return distribution

def get_language_distribution_in_range(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None) -> Dict[str, int]:
    """Gets job counts per detected language within a date range (includes hidden, finished jobs only)."""
    sql = "SELECT detected_language, COUNT(*) as count FROM transcriptions WHERE status = 'finished'"
    params = []
    if start_dt:
        sql += " AND created_at >= %s"
        params.append(start_dt.isoformat(timespec='seconds'))
    if end_dt:
        sql += " AND created_at < %s"
        params.append(end_dt.isoformat(timespec='seconds'))

    sql += " GROUP BY detected_language"

    cursor = get_cursor()
    distribution = {}
    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        for row in rows:
            lang = row['detected_language'] or 'Unknown'
            distribution[lang] = int(row['count']) if row['count'] is not None else 0
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] Error getting language distribution: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return distribution

def get_common_error_messages_in_range(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Gets the most common transcription error messages and their counts within a date range (includes hidden)."""
    sql = """
        SELECT error_message, COUNT(*) as count
        FROM transcriptions
        WHERE status = 'error' AND error_message IS NOT NULL AND error_message != ''
    """
    params = []
    if start_dt:
        sql += " AND created_at >= %s"
        params.append(start_dt.isoformat(timespec='seconds'))
    if end_dt:
        sql += " AND created_at < %s"
        params.append(end_dt.isoformat(timespec='seconds'))

    sql += " GROUP BY error_message ORDER BY count DESC LIMIT %s"
    params.append(limit)

    cursor = get_cursor()
    errors = []
    try:
        cursor.execute(sql, tuple(params))
        errors = cursor.fetchall()
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] Error getting common transcription error messages: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return errors

# --- Workflow Metrics Functions ---
def get_workflow_model_distribution(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None, include_attempted: bool = False) -> Dict[str, int]:
    """
    Gets workflow counts per model used within a date range.
    Uses 'llm_operation_status' from the 'transcriptions' table and joins with 'llm_operations'
    to get the provider (model name).
    """
    status_filter_column_on_t = 't.llm_operation_status'
    status_filter = f"{status_filter_column_on_t} != 'idle'" if include_attempted else f"{status_filter_column_on_t} = 'finished'"
    date_column_on_t = f"t.{'llm_operation_ran_at' if not include_attempted else 'created_at'}"

    sql = f"""
        SELECT
            lo.provider AS llm_operation_model_used,
            COUNT(t.id) AS count
        FROM transcriptions t
        JOIN llm_operations lo ON t.llm_operation_id = lo.id
        WHERE
            lo.operation_type = 'workflow' 
            AND {status_filter}
    """
    params = []

    if start_dt:
        sql += f" AND {date_column_on_t} >= %s"
        params.append(start_dt.isoformat(timespec='seconds'))
    if end_dt:
        sql += f" AND {date_column_on_t} < %s"
        params.append(end_dt.isoformat(timespec='seconds'))

    sql += " GROUP BY lo.provider"

    cursor = get_cursor()
    distribution = {}
    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        for row in rows:
            model = row['llm_operation_model_used'] or 'Unknown'
            distribution[model] = int(row['count']) if row['count'] is not None else 0
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] MySQL Error getting workflow model distribution (Attempted={include_attempted}): {err.errno} ({err.sqlstate}) - {err.msg}", exc_info=True)
        if err.errno == 1054:
            logging.warning(f"[DB:AdminUtils] Error getting workflow model distribution: A column might be missing in the join. {err.msg}")
        return {}
    except Exception as e:
        logging.error(f"[DB:AdminUtils] Unexpected error getting workflow model distribution (Attempted={include_attempted}): {e}", exc_info=True)
        return {}
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return distribution

def get_common_workflow_error_messages(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Gets the most common workflow error messages and their counts within a date range (includes hidden).
    Uses 'llm_operation_status' and 'llm_operation_error'.
    """
    sql = """
        SELECT llm_operation_error, COUNT(*) as count
        FROM transcriptions
        WHERE llm_operation_status = 'error' AND llm_operation_error IS NOT NULL AND llm_operation_error != ''
    """
    params = []
    if start_dt:
        sql += " AND created_at >= %s" 
        params.append(start_dt.isoformat(timespec='seconds'))
    if end_dt:
        sql += " AND created_at < %s"
        params.append(end_dt.isoformat(timespec='seconds'))

    sql += " GROUP BY llm_operation_error ORDER BY count DESC LIMIT %s"
    params.append(limit)

    cursor = get_cursor()
    errors = []
    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        for row in rows:
            errors.append({'error_message': row['llm_operation_error'], 'count': row['count']})
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] Error getting common workflow error messages: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return errors

# --- NEW: Pagination Functions ---
def count_visible_user_transcriptions(user_id: int) -> int:
    """Counts the total number of *visible* and *finished* transcription records for a user."""
    log_prefix = f"[DB:History:User:{user_id}]"
    sql = 'SELECT COUNT(*) as count FROM transcriptions WHERE user_id = %s AND is_hidden_from_user = FALSE AND status = %s'
    cursor = None
    count = 0
    try:
        cursor = get_cursor()
        cursor.execute(sql, (user_id, 'finished'))
        result = cursor.fetchone()
        count = result['count'] if result else 0
        logging.debug(f"{log_prefix} Counted {count} visible and finished transcriptions.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error counting visible transcriptions: {err}", exc_info=True)
        count = 0
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count

def get_paginated_transcriptions(user_id: int, page: int, per_page: int) -> List[Dict[str, Any]]:
    """
    Retrieves a paginated list of visible and finished transcription records for a user,
    ordered by creation date DESC. Includes the latest associated LLM operation ID.
    """
    log_prefix = f"[DB:History:User:{user_id}:Page:{page}]"
    offset = (page - 1) * per_page

    sql = """
        WITH RankedOperations AS (
            SELECT
                lo.id AS llm_operation_id,
                lo.transcription_id,
                ROW_NUMBER() OVER(PARTITION BY lo.transcription_id ORDER BY lo.completed_at DESC, lo.created_at DESC) as rn
            FROM llm_operations lo
            WHERE lo.user_id = %s
              AND lo.operation_type = 'workflow'
              AND lo.status IN ('finished', 'error')
        )
        SELECT
            t.*,
            ro.llm_operation_id
        FROM transcriptions t
        LEFT JOIN RankedOperations ro ON t.id = ro.transcription_id AND ro.rn = 1
        WHERE t.user_id = %s AND t.is_hidden_from_user = FALSE AND t.status = %s
        ORDER BY t.created_at DESC
        LIMIT %s OFFSET %s
    """
    params = (user_id, user_id, 'finished', per_page, offset)

    transcriptions = []
    cursor = get_cursor()
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        transcriptions = [_map_row_to_transcription_dict(row) for row in rows if row]
        logging.debug(f"{log_prefix} Retrieved {len(transcriptions)} visible and finished transcription records for page {page} (limit={per_page}, offset={offset}).")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving paginated transcriptions: {err}", exc_info=True)
        transcriptions = []
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return transcriptions

def count_successful_title_generations_in_range(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None, user_id: Optional[int] = None) -> int:
    """Counts finished jobs with successful title generation within a date range, optionally for a specific user."""
    filters = {'status': 'finished', 'title_generation_status': 'success'}
    if user_id is not None:
        filters['user_id'] = user_id
    return count_jobs_in_range(start_dt, end_dt, **filters)

# --- NEW: Function to count workflow jobs with specific filters ---
def count_workflow_jobs_with_filters(
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    transcription_status_in: Optional[Tuple[str, ...]] = None,
    llm_operation_status: Optional[str] = None,
    llm_provider: Optional[str] = None
) -> int:
    """
    Counts transcription jobs that have associated workflow operations matching the given criteria.
    Joins transcriptions with llm_operations.
    """
    sql = """
        SELECT COUNT(t.id) as count
        FROM transcriptions t
        JOIN llm_operations lo ON t.llm_operation_id = lo.id
        WHERE lo.operation_type = 'workflow'
    """
    params = []
    log_prefix = "[DB:AdminUtils:CountWorkflowJobs]"

    # Date filters are applied to the transcription creation time for consistency with other metrics
    if start_dt:
        sql += " AND t.created_at >= %s"
        params.append(start_dt.isoformat(timespec='seconds'))
    if end_dt:
        sql += " AND t.created_at < %s"
        params.append(end_dt.isoformat(timespec='seconds'))

    if transcription_status_in:
        if not isinstance(transcription_status_in, (list, tuple)) or not transcription_status_in:
            logging.warning(f"{log_prefix} Invalid transcription_status_in: {transcription_status_in}. Skipping filter.")
        else:
            placeholders = ', '.join(['%s'] * len(transcription_status_in))
            sql += f" AND t.status IN ({placeholders})"
            params.extend(list(transcription_status_in))

    if llm_operation_status:
        sql += " AND lo.status = %s"
        params.append(llm_operation_status)

    if llm_provider:
        sql += " AND lo.provider = %s"
        params.append(llm_provider)

    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql, tuple(params))
        result = cursor.fetchone()
        if result:
            count = result['count']
        logging.debug(f"{log_prefix} Counted {count} workflow jobs with filters: status_in={transcription_status_in}, op_status={llm_operation_status}, provider={llm_provider}")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error counting workflow jobs with filters: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count
# --- END NEW ---

def get_cost_analytics_by_component(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None, user_id: Optional[int] = None) -> Dict[str, float]:
    """
    Calculates the total cost for transcriptions, title generations, and workflows within a date range.
    Can be filtered by a specific user_id.
    """
    log_prefix = f"[DB:AdminUtils:CostAnalytics:User:{user_id or 'All'}]"
    costs = {'transcriptions': 0.0, 'title_generations': 0.0, 'workflows': 0.0}

    # Base SQL for date and user filtering
    date_filter_sql = ""
    params = []
    if start_dt:
        date_filter_sql += " AND created_at >= %s"
        params.append(start_dt.isoformat(timespec='seconds'))
    if end_dt:
        date_filter_sql += " AND created_at < %s"
        params.append(end_dt.isoformat(timespec='seconds'))

    user_filter_sql = ""
    user_params = []
    if user_id is not None:
        user_filter_sql = " AND user_id = %s"
        user_params.append(user_id)

    # Diagnostic logging for filters and params
    try:
        logging.debug(f"{log_prefix} Computing cost analytics. start_dt={start_dt}, end_dt={end_dt}, user_id={user_id}")
        logging.debug(f"{log_prefix} date_filter_sql='{date_filter_sql}', user_filter_sql='{user_filter_sql}', params={params}, user_params={user_params}")
    except Exception as _:
        # Ensure logging never interrupts execution
        pass

    cursor = get_cursor()
    try:
        # Transcriptions cost
        sql_transcriptions = f"SELECT SUM(cost) as total_cost FROM transcriptions WHERE cost IS NOT NULL{date_filter_sql}{user_filter_sql}"
        try:
            logging.debug(f"{log_prefix} Executing SQL (transcriptions): {sql_transcriptions} | params={tuple(params + user_params)}")
        except Exception:
            pass

        cursor.execute(sql_transcriptions, tuple(params + user_params))
        result = cursor.fetchone()
        try:
            logging.debug(f"{log_prefix} Fetched transcriptions cost row: {result}")
        except Exception:
            pass

        if result and result.get('total_cost') is not None:
            try:
                costs['transcriptions'] = float(result['total_cost'])
            except Exception:
                logging.warning(f"{log_prefix} Unable to cast transcriptions total_cost '{result.get('total_cost')}' to float.")
        else:
            logging.debug(f"{log_prefix} Transcriptions SUM(cost) returned NULL or 0.")

        # Title generations and workflows cost (from llm_operations)
        sql_llm = f"SELECT operation_type, SUM(cost) as total_cost FROM llm_operations WHERE cost IS NOT NULL{date_filter_sql}{user_filter_sql} GROUP BY operation_type"
        try:
            logging.debug(f"{log_prefix} Executing SQL (llm_operations): {sql_llm} | params={tuple(params + user_params)}")
        except Exception:
            pass

        cursor.execute(sql_llm, tuple(params + user_params))
        rows = cursor.fetchall()
        try:
            logging.debug(f"{log_prefix} Fetched llm_operations grouped rows: {rows}")
        except Exception:
            pass

        for row in rows or []:
            op_type = row.get('operation_type')
            total_cost = row.get('total_cost')
            if total_cost is None:
                continue
            if op_type == 'title_generation':
                costs['title_generations'] = float(total_cost)
            elif op_type == 'workflow':
                costs['workflows'] = float(total_cost)

        # Final diagnostics
        try:
            logging.debug(f"{log_prefix} Aggregated component costs => transcriptions={costs['transcriptions']}, title_generations={costs['title_generations']}, workflows={costs['workflows']}")
        except Exception:
            pass

    except MySQLError as err:
        logging.error(f"{log_prefix} Error calculating cost analytics by component: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return costs

def get_cost_analytics_by_role(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
    """
    Calculates the total cost and user count per role within a date range.
    """
    log_prefix = "[DB:AdminUtils:CostAnalyticsByRole]"
    costs_by_role = {}

    # Base SQL for date filtering
    date_filter_sql = ""
    params = []
    if start_dt:
        date_filter_sql += " AND t.created_at >= %s"
        params.append(start_dt.isoformat(timespec='seconds'))
    if end_dt:
        date_filter_sql += " AND t.created_at < %s"
        params.append(end_dt.isoformat(timespec='seconds'))

    cursor = get_cursor()
    try:
        # Get costs from both tables, grouped by role
        sql = f"""
            SELECT r.name as role_name, SUM(total_cost) as total_cost, COUNT(DISTINCT u.id) as user_count
            FROM roles r
            JOIN users u ON r.id = u.role_id
            LEFT JOIN (
                SELECT user_id, cost as total_cost, created_at FROM transcriptions WHERE cost IS NOT NULL
                UNION ALL
                SELECT user_id, cost as total_cost, created_at FROM llm_operations WHERE cost IS NOT NULL
            ) as costs ON u.id = costs.user_id
            WHERE costs.total_cost IS NOT NULL{date_filter_sql.replace('created_at', 'costs.created_at')}
            GROUP BY r.name
        """
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        for row in rows:
            costs_by_role[row['role_name']] = {
                'total_cost': float(row['total_cost']),
                'user_count': int(row['user_count'])
            }

    except MySQLError as err:
        logging.error(f"{log_prefix} Error calculating cost analytics by role: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return costs_by_role