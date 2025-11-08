"""
User-specific transcription statistics helpers.
"""

import logging
from typing import Any

from mysql.connector import Error as MySQLError

from app.database import get_cursor


def _count_by_query(sql: str, params: Any, log_prefix: str, description: str) -> int:
    cursor = get_cursor()
    count = 0
    try:
        cursor.execute(sql, params)
        result = cursor.fetchone()
        cursor.fetchall()
        count = result['count'] if result else 0
        logging.debug("%s %s %s records.", log_prefix, description, count)
    except MySQLError as err:
        logging.error("%s Error %s: %s", log_prefix, description, err, exc_info=True)
        count = 0
    return count


def count_user_transcriptions(user_id: int) -> int:
    """Counts the total number of transcription records for a user (including hidden)."""
    log_prefix = f"[DB:Stats:User:{user_id}]"
    sql = 'SELECT COUNT(*) as count FROM transcriptions WHERE user_id = %s'
    return _count_by_query(sql, (user_id,), log_prefix, "Counted total transcriptions (including hidden):")


def count_user_errors(user_id: int) -> int:
    """Counts the number of transcription records with status 'error' for a user."""
    log_prefix = f"[DB:Stats:User:{user_id}]"
    sql = "SELECT COUNT(*) as count FROM transcriptions WHERE user_id = %s AND status = 'error'"
    return _count_by_query(sql, (user_id,), log_prefix, "Counted errored transcriptions (including hidden):")


def get_total_audio_length_in_minutes(user_id: int) -> float:
    """
    Calculates the sum of 'audio_length_minutes' for all transcription records
    belonging to a specific user where the length is not NULL (including hidden).
    """
    log_prefix = f"[DB:Stats:User:{user_id}]"
    sql = (
        "SELECT SUM(audio_length_minutes) as total_minutes "
        "FROM transcriptions WHERE user_id = %s AND audio_length_minutes IS NOT NULL"
    )
    cursor = get_cursor()
    total_minutes = 0.0
    try:
        cursor.execute(sql, (user_id,))
        result = cursor.fetchone()
        cursor.fetchall()
        total_minutes = (
            result['total_minutes'] if result and result['total_minutes'] is not None else 0.0
        )
        logging.debug(
            "%s Calculated total audio length (including hidden): %.2f minutes",
            log_prefix,
            total_minutes,
        )
        return float(total_minutes)
    except MySQLError as err:
        logging.error(
            "%s Error calculating total audio length in minutes: %s",
            log_prefix,
            err,
            exc_info=True,
        )
        total_minutes = 0.0
    return total_minutes


__all__ = [
    "count_user_transcriptions",
    "count_user_errors",
    "get_total_audio_length_in_minutes",
]
