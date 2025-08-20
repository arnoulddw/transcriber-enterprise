# app/services/usage_service.py
# This file contains functions for calculating user usage statistics.

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from app.database import get_cursor

def get_user_usage(user_id: int) -> Dict[str, Any]:
    """
    Calculates a user's usage for the last day, week, and month.

    Args:
        user_id: The ID of the user.

    Returns:
        A dictionary with the user's usage stats.
    """
    log_prefix = f"[UsageService:User:{user_id}]"
    cursor = get_cursor()
    
    today = datetime.now(timezone.utc).date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    usage_stats = {
        'daily': {'cost': 0, 'minutes': 0, 'workflows': 0},
        'weekly': {'cost': 0, 'minutes': 0, 'workflows': 0},
        'monthly': {'cost': 0, 'minutes': 0, 'workflows': 0},
    }

    try:
        # Daily usage
        cursor.execute(
            "SELECT SUM(cost) as cost, SUM(minutes) as minutes, SUM(workflows) as workflows FROM user_usage WHERE user_id = %s AND date = %s",
            (user_id, today)
        )
        daily_usage = cursor.fetchone()
        if daily_usage and daily_usage['cost'] is not None:
            usage_stats['daily'] = {
                'cost': float(daily_usage['cost']),
                'minutes': int(daily_usage['minutes']),
                'workflows': int(daily_usage['workflows']),
            }

        # Weekly usage
        cursor.execute(
            "SELECT SUM(cost) as cost, SUM(minutes) as minutes, SUM(workflows) as workflows FROM user_usage WHERE user_id = %s AND date >= %s",
            (user_id, start_of_week)
        )
        weekly_usage = cursor.fetchone()
        if weekly_usage and weekly_usage['cost'] is not None:
            usage_stats['weekly'] = {
                'cost': float(weekly_usage['cost']),
                'minutes': int(weekly_usage['minutes']),
                'workflows': int(weekly_usage['workflows']),
            }

        # Monthly usage
        cursor.execute(
            "SELECT SUM(cost) as cost, SUM(minutes) as minutes, SUM(workflows) as workflows FROM user_usage WHERE user_id = %s AND date >= %s",
            (user_id, start_of_month)
        )
        monthly_usage = cursor.fetchone()
        if monthly_usage and monthly_usage['cost'] is not None:
            usage_stats['monthly'] = {
                'cost': float(monthly_usage['cost']),
                'minutes': int(monthly_usage['minutes']),
                'workflows': int(monthly_usage['workflows']),
            }
            
    except Exception as e:
        logging.error(f"{log_prefix} Error calculating usage stats: {e}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

    return usage_stats