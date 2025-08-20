# app/tasks/cleanup.py
# Defines the background task for cleaning up old files and purging user history.

import os
import time
import logging
import threading # For potential future use if task logic becomes complex
from datetime import datetime, timezone
from typing import Optional, Any # Keep this import for Role type hint

# Import necessary services and models
from app.services import file_service
# <<< MODIFIED: Import both transcription and transcription_utils >>>
from app.models import transcription as transcription_model
from app.models import transcription_utils # Import the new utils file
# <<< END MODIFIED >>>
from app.models import user as user_model # Uses MySQL now
from app.models.role import Role # Import Role for type hint

# Import Flask type hint
from flask import Flask

# Import MySQL error class for potential specific checks if needed
from mysql.connector import Error as MySQLError

# Modify function signature to accept the Flask app object
def run_cleanup_task(app: Flask) -> None:
    """
    The main function for the background cleanup task.
    Periodically cleans old uploaded files and purges user transcription history based on role limits.
    This function is intended to run in a separate thread and requires the Flask app instance.

    Args:
        app: The Flask application instance.
    """
    initial_wait_seconds = 20
    logging.debug(f"[TASK:Cleanup] Cleanup thread started (PID: {os.getpid()}). Waiting {initial_wait_seconds}s for app startup...")
    time.sleep(initial_wait_seconds)
    logging.debug(f"[TASK:Cleanup] Initial wait complete. Starting periodic cleanup loop.")

    sleep_interval_seconds = 6 * 60 * 60

    while True:
        log_prefix = f"[TASK:Cleanup:PID:{os.getpid()}]"
        logging.debug(f"{log_prefix} Starting cleanup cycle at {datetime.now(timezone.utc).isoformat()}Z.")

        try:
            # Ensure operations run within the Flask application context
            with app.app_context():
                config = app.config

                # --- 1. Old File Cleanup ---
                upload_dir = config['TEMP_UPLOADS_DIR']
                threshold = config.get('DELETE_THRESHOLD', 24 * 60 * 60) # Default 24h
                logging.debug(f"{log_prefix} Running periodic file cleanup in '{upload_dir}' (Threshold: {threshold}s)...")
                try:
                    deleted_count = file_service.cleanup_old_files(upload_dir, threshold)
                    if deleted_count > 0:
                        logging.info(f"{log_prefix} File cleanup finished. Deleted {deleted_count} old file(s).")
                    else:
                        logging.debug(f"{log_prefix} File cleanup finished. Deleted 0 old file(s).")
                except Exception as file_err:
                    logging.error(f"{log_prefix} Error during file cleanup: {file_err}", exc_info=True)

                # --- 2. User History Purging (Soft Delete) ---
                logging.debug(f"{log_prefix} Running periodic history cleanup (soft delete)...")
                total_hidden_history = 0
                try:
                    # Fetch all users (uses MySQL now)
                    all_users = user_model.get_all_users()
                    logging.debug(f"{log_prefix} Found {len(all_users)} users for history check.")

                    for user in all_users:
                        user_log_prefix = f"{log_prefix}:User:{user.id}"
                        try:
                            # Access role property (triggers lazy load using MySQL now)
                            role: Optional[Role] = user.role
                            if role:
                                max_items = role.max_history_items
                                retention_days = role.history_retention_days

                                if max_items > 0 or retention_days > 0:
                                    logging.debug(f"{user_log_prefix} Checking history limits (Role: {role.name}, MaxItems: {max_items}, RetentionDays: {retention_days})")
                                    # <<< MODIFIED: Call purge function from transcription_utils >>>
                                    hidden_count = transcription_utils.purge_user_history(user.id, max_items, retention_days)
                                    # <<< END MODIFIED >>>

                                    if hidden_count > 0:
                                        total_hidden_history += hidden_count
                                        logging.info(f"{user_log_prefix} Hid {hidden_count} history records based on retention policy.")
                                    elif hidden_count == 0:
                                         logging.debug(f"{user_log_prefix} No history records needed hiding for this user.")
                                    else: # hidden_count == -1 indicates an error during purge
                                        logging.error(f"{user_log_prefix} Error occurred during history hiding (check model logs).")
                                else:
                                    logging.debug(f"{user_log_prefix} No history limits set for role '{role.name}'. Skipping history hiding.")
                            else:
                                logging.warning(f"{user_log_prefix} User has no role assigned. Skipping history hiding.")
                        except MySQLError as user_db_err: # Catch potential DB errors during user processing
                             logging.error(f"{user_log_prefix} DB error processing history hiding for this user: {user_db_err}", exc_info=True)
                        except Exception as user_purge_err:
                             logging.error(f"{user_log_prefix} Error processing history hiding for this user: {user_purge_err}", exc_info=True)

                    if total_hidden_history > 0:
                        logging.info(f"{log_prefix} History hiding finished. Hid {total_hidden_history} records in total across all users.")
                    else:
                        logging.debug(f"{log_prefix} History hiding finished. Hid 0 records in total.")

                except MySQLError as history_db_err: # Catch DB errors getting all users or during purge loop
                    logging.error(f"{log_prefix} DB error during history hiding process: {history_db_err}", exc_info=True)
                except Exception as history_err:
                    logging.error(f"{log_prefix} Error during history hiding process: {history_err}", exc_info=True)

                # --- 3. Physical Deletion of Old Hidden Records ---
                physical_delete_days = config.get('PHYSICAL_DELETION_DAYS', 120)
                logging.debug(f"{log_prefix} Running physical deletion of records hidden for more than {physical_delete_days} days...")
                total_physically_deleted = 0
                try:
                    # <<< MODIFIED: Call physical delete function from transcription_utils >>>
                    deleted_count = transcription_utils.physically_delete_hidden_records(physical_delete_days)
                    # <<< END MODIFIED >>>
                    if deleted_count > 0:
                        total_physically_deleted = deleted_count
                        logging.info(f"{log_prefix} Physically deleted {total_physically_deleted} old hidden records.")
                    elif deleted_count == 0:
                        logging.debug(f"{log_prefix} No old hidden records found for physical deletion.")
                    else: # deleted_count == -1 indicates an error
                        logging.error(f"{log_prefix} Error occurred during physical deletion (check model logs).")
                except MySQLError as physical_del_db_err:
                    logging.error(f"{log_prefix} DB error during physical deletion: {physical_del_db_err}", exc_info=True)
                except Exception as physical_del_err:
                    logging.error(f"{log_prefix} Error during physical deletion: {physical_del_err}", exc_info=True)

        except Exception as cycle_err:
            # Catch errors occurring outside the specific cleanup steps (e.g., getting app context)
            try:
                logging.error(f"{log_prefix} Error during cleanup task cycle: {cycle_err}", exc_info=True)
            except Exception:
                print(f"CRITICAL [TASK:Cleanup]: Logging failed during cleanup task error: {cycle_err}", flush=True)

        # --- Sleep until the next cycle ---
        try:
            logging.debug(f"{log_prefix} Cleanup cycle finished. Sleeping for {sleep_interval_seconds} seconds...")
        except Exception:
             print(f"INFO [TASK:Cleanup]: Cleanup cycle finished. Sleeping...", flush=True) # Fallback print

        time.sleep(sleep_interval_seconds)