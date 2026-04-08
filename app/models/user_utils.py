# ./app/models/user_utils.py
# Contains utility functions for user data, including stats, admin views, and analytics.

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

# Import MySQL specific error class
from mysql.connector import Error as MySQLError

# Import centralized DB functions (now MySQL based)
from app.database import get_cursor

# Import User class for type hinting and related functions if needed
try:
    from .user import User, get_user_by_id, _map_row_to_user # Import User for type hint, get_user_by_id for usage stats
except ImportError as e:
    logging.critical(f"[DB:Models:UserUtils] Failed to import User model dependencies: {e}. This may cause runtime errors.")
    User = None # type: ignore
    get_user_by_id = None # type: ignore


# --- User Usage Stats ---

def get_user_usage_stats(user_id: int) -> Dict[str, Any]:
    """
    Retrieves user's total and monthly usage stats by aggregating from the 'user_usage' table.
    """
    default_stats = {
        'total_transcriptions': 0, 'total_minutes': 0.0,
        'monthly_transcriptions': 0, 'monthly_minutes': 0.0,
        'monthly_workflows': 0
    }
    cursor = get_cursor()
    try:
        # Get total and monthly aggregates in one go
        now = datetime.now(timezone.utc)
        start_of_month = now.date().replace(day=1)
        
        query = """
            SELECT
                SUM(minutes) AS total_minutes,
                SUM(workflows) AS total_workflows,
                SUM(CASE WHEN date >= %s THEN minutes ELSE 0 END) AS monthly_minutes,
                SUM(CASE WHEN date >= %s THEN workflows ELSE 0 END) AS monthly_workflows
            FROM user_usage
            WHERE user_id = %s
        """
        cursor.execute(query, (start_of_month, start_of_month, user_id))
        usage_data = cursor.fetchone()

        # Get total transcriptions separately
        cursor.execute("SELECT COUNT(*) as count FROM transcriptions WHERE user_id = %s", (user_id,))
        transcription_data = cursor.fetchone()

        stats = {
            'total_transcriptions': transcription_data['count'] if transcription_data else 0,
            'total_minutes': float(usage_data['total_minutes']) if usage_data and usage_data['total_minutes'] else 0.0,
            'monthly_transcriptions': 0,  # This metric is no longer tracked
            'monthly_minutes': float(usage_data['monthly_minutes']) if usage_data and usage_data['monthly_minutes'] else 0.0,
            'monthly_workflows': int(usage_data['monthly_workflows']) if usage_data and usage_data['monthly_workflows'] else 0
        }
        return stats
    except MySQLError as err:
        logging.error(f"[DB:UserUtils:{user_id}] Error getting usage stats: {err}", exc_info=True)
        return default_stats
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass


# --- Admin Panel Functions ---

def count_all_users() -> int:
    """Counts the total number of registered users."""
    sql = 'SELECT COUNT(*) as count FROM users'
    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql)
        result = cursor.fetchone()
        count = result['count'] if result else 0
        logging.debug(f"[DB:AdminUtils] Counted {count} total users.")
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] Error counting all users: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count

def get_paginated_users_with_details(offset: int, limit: int) -> List[User]:
    """
    Retrieves a paginated list of User objects with details for the admin panel.
    Uses JOINs + GROUP BY instead of correlated subqueries for O(N) rather than O(N*M).
    """
    users_data = []
    sql = """
        SELECT
            u.*,
            r.name as role_name,
            COALESCE(tc.total_transcriptions, 0)  AS total_transcriptions,
            COALESCE(uu.total_workflows, 0)        AS total_workflows,
            COALESCE(uu.total_minutes, 0.0)        AS total_minutes
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS total_transcriptions
            FROM transcriptions
            GROUP BY user_id
        ) tc ON tc.user_id = u.id
        LEFT JOIN (
            SELECT user_id, SUM(workflows) AS total_workflows, SUM(minutes) AS total_minutes
            FROM user_usage
            GROUP BY user_id
        ) uu ON uu.user_id = u.id
        ORDER BY u.id ASC
        LIMIT %s OFFSET %s
    """
    cursor = get_cursor()
    try:
        cursor.execute(sql, (limit, offset))
        rows = cursor.fetchall()
        for row in rows:
            user = _map_row_to_user(row)
            if user:
                user.role_name = row.get('role_name')
                user.total_transcriptions = row.get('total_transcriptions', 0)
                user.total_workflows = row.get('total_workflows', 0)
                user.total_minutes = row.get('total_minutes', 0.0)
                users_data.append(user)

        logging.debug(f"[DB:AdminUtils] Retrieved {len(users_data)} User objects for pagination (limit={limit}, offset={offset}).")
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] Error retrieving paginated users: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return users_data


# --- Admin Analytics Functions ---

def count_active_users_in_range(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None) -> int:
    """Counts distinct users who submitted a job within a date range."""
    sql = "SELECT COUNT(DISTINCT user_id) as count FROM transcriptions WHERE 1=1"
    params = []
    if start_dt:
        sql += " AND created_at >= %s"
        params.append(start_dt.isoformat(timespec='seconds'))
    if end_dt:
        sql += " AND created_at < %s"
        params.append(end_dt.isoformat(timespec='seconds'))

    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql, tuple(params))
        result = cursor.fetchone()
        count = result['count'] if result else 0
        logging.debug(f"[DB:AdminUtils] Counted {count} active users in range ({start_dt} - {end_dt}).")
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] Error counting active users in range ({start_dt} - {end_dt}): {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count

def count_new_users_in_range(start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None) -> int:
    """Counts users created within a date range."""
    sql = "SELECT COUNT(*) as count FROM users WHERE 1=1"
    params = []
    if start_dt:
        sql += " AND created_at >= %s"
        params.append(start_dt.isoformat(timespec='seconds'))
    if end_dt:
        sql += " AND created_at < %s"
        params.append(end_dt.isoformat(timespec='seconds'))

    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql, tuple(params))
        result = cursor.fetchone()
        count = result['count'] if result else 0
        logging.debug(f"[DB:AdminUtils] Counted {count} new users in range ({start_dt} - {end_dt}).")
    except MySQLError as err:
        logging.error(f"[DB:AdminUtils] Error counting new users in range ({start_dt} - {end_dt}): {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return count

def get_users_hitting_limits() -> List[Dict[str, Any]]:
    """
    Identifies users who have hit their monthly or total transcription/minute/workflow limits.
    Returns a list of dictionaries containing user ID, username, role name, and the limit hit.
    """
    users_hitting_limits = []
    log_prefix = "[DB:AdminUtils:Limits]"
    now = datetime.now(timezone.utc)
    start_of_month = now.date().replace(day=1)

    # Use CTEs to compute per-user aggregates once, then filter in the outer query.
    # This replaces 11 correlated subqueries that previously ran per-row.
    sql = """
        WITH transcription_totals AS (
            SELECT user_id, COUNT(*) AS total_transcriptions
            FROM transcriptions
            GROUP BY user_id
        ),
        transcription_monthly AS (
            SELECT user_id, COUNT(*) AS monthly_transcriptions
            FROM transcriptions
            WHERE created_at >= %s
            GROUP BY user_id
        ),
        usage_totals AS (
            SELECT user_id,
                   SUM(minutes)   AS total_minutes,
                   SUM(workflows) AS total_workflows
            FROM user_usage
            GROUP BY user_id
        ),
        usage_monthly AS (
            SELECT user_id,
                   SUM(minutes)   AS monthly_minutes,
                   SUM(workflows) AS monthly_workflows
            FROM user_usage
            WHERE date >= %s
            GROUP BY user_id
        )
        SELECT
            u.id,
            u.username,
            r.name                                         AS role_name,
            r.max_transcriptions_total,
            r.max_minutes_total,
            r.max_transcriptions_monthly,
            r.max_minutes_monthly,
            r.max_workflows_total,
            r.max_workflows_monthly,
            COALESCE(tt.total_transcriptions, 0)           AS total_transcriptions,
            COALESCE(ut.total_minutes, 0)                  AS total_minutes,
            COALESCE(ut.total_workflows, 0)                AS total_workflows,
            COALESCE(tm.monthly_transcriptions, 0)         AS monthly_transcriptions,
            COALESCE(um.monthly_minutes, 0)                AS monthly_minutes,
            COALESCE(um.monthly_workflows, 0)              AS monthly_workflows
        FROM users u
        JOIN roles r ON u.role_id = r.id
        LEFT JOIN transcription_totals  tt ON tt.user_id = u.id
        LEFT JOIN transcription_monthly tm ON tm.user_id = u.id
        LEFT JOIN usage_totals          ut ON ut.user_id = u.id
        LEFT JOIN usage_monthly         um ON um.user_id = u.id
        WHERE
            (r.max_transcriptions_total   > 0 AND COALESCE(tt.total_transcriptions,  0) >= r.max_transcriptions_total)
            OR (r.max_minutes_total       > 0 AND COALESCE(ut.total_minutes,         0) >= r.max_minutes_total)
            OR (r.max_transcriptions_monthly > 0 AND COALESCE(tm.monthly_transcriptions, 0) >= r.max_transcriptions_monthly)
            OR (r.max_minutes_monthly     > 0 AND COALESCE(um.monthly_minutes,       0) >= r.max_minutes_monthly)
            OR (r.max_workflows_monthly   > 0 AND COALESCE(um.monthly_workflows,     0) >= r.max_workflows_monthly)
        ORDER BY u.id
    """
    cursor = get_cursor()
    try:
        cursor.execute(sql, (start_of_month, start_of_month))
        rows = cursor.fetchall()
        for row in rows:
            limit_hit = []
            # Transcription Limits
            total_transcriptions = row.get('total_transcriptions', 0) or 0
            if row['max_transcriptions_total'] > 0 and total_transcriptions >= row['max_transcriptions_total']:
                limit_hit.append({'name': 'Total Transcriptions', 'value': total_transcriptions, 'limit': row['max_transcriptions_total']})
            
            total_minutes = row.get('total_minutes', 0.0) or 0.0
            if row['max_minutes_total'] > 0 and total_minutes >= row['max_minutes_total']:
                limit_hit.append({'name': 'Total Minutes', 'value': f"{total_minutes:.1f}", 'limit': row['max_minutes_total']})

            monthly_transcriptions = row.get('monthly_transcriptions', 0) or 0
            if row['max_transcriptions_monthly'] > 0 and monthly_transcriptions >= row['max_transcriptions_monthly']:
                limit_hit.append({'name': 'Monthly Transcriptions', 'value': monthly_transcriptions, 'limit': row['max_transcriptions_monthly']})

            monthly_minutes = row.get('monthly_minutes', 0.0) or 0.0
            if row['max_minutes_monthly'] > 0 and monthly_minutes >= row['max_minutes_monthly']:
                limit_hit.append({'name': 'Monthly Minutes', 'value': f"{monthly_minutes:.1f}", 'limit': row['max_minutes_monthly']})

            total_workflows = row.get('total_workflows', 0) or 0
            if row['max_workflows_total'] > 0 and total_workflows >= row['max_workflows_total']:
                limit_hit.append({'name': 'Total Workflows', 'value': total_workflows, 'limit': row['max_workflows_total']})

            monthly_workflows = row.get('monthly_workflows', 0) or 0
            if row['max_workflows_monthly'] > 0 and monthly_workflows >= row['max_workflows_monthly']:
                limit_hit.append({'name': 'Monthly Workflows', 'value': monthly_workflows, 'limit': row['max_workflows_monthly']})

            if limit_hit:
                users_hitting_limits.append({
                    'id': row['id'],
                    'username': row['username'],
                    'role_name': row['role_name'],
                    'limits_hit': limit_hit
                })
        logging.debug(f"{log_prefix} Found {len(users_hitting_limits)} users hitting limits.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error getting users hitting limits: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return users_hitting_limits