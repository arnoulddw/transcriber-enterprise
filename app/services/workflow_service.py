# app/services/workflow_service.py
# Contains business logic for AI-powered workflow analysis on transcripts.

from app.logging_config import get_logger
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from flask import current_app, Flask

# Import models
from app.models import transcription as transcription_model
from app.models import user as user_model
from app.models import role as role_model
from app.models import llm_operation as llm_operation_model
from app.models import user_prompt as user_prompt_model
from app.models import template_prompt as template_prompt_model
from app.models.user import User  # For type hinting

from app.services import llm_service
from app.services.api_clients.exceptions import LlmApiError, LlmConfigurationError, LlmGenerationError, LlmSafetyError, LlmRateLimitError

# Import permission checking helpers
from app.core.decorators import check_permission, check_usage_limits

# Import MySQL error class
from mysql.connector import Error as MySQLError

# Import centralized DB functions (needed for direct updates if any remain)
from app.database import get_db, get_cursor

# --- Custom Exceptions ---
class WorkflowError(Exception):
    """Base exception for workflow service errors."""
    pass

class PermissionDeniedError(WorkflowError):
    """User does not have permission."""
    pass

class UsageLimitExceededError(WorkflowError):
    """User has exceeded workflow usage limits."""
    pass

class TranscriptionNotFoundError(WorkflowError):
    """Transcription record not found."""
    pass

class OperationNotFoundError(WorkflowError):
    """LLM Operation record not found."""
    pass

class InvalidPromptError(WorkflowError):
    """Prompt is invalid (e.g., too long, or ID not found)."""
    pass

class WorkflowInProgressError(WorkflowError):
    """Another workflow is already running for this transcription."""
    pass

# --- Core Workflow Functions ---

def start_workflow(user_id: int, transcription_id: str, prompt: Optional[str], prompt_id: Optional[int] = None) -> int:
    """
    Validates request and initiates the background workflow process.
    Creates an LLMOperation record to track the task.
    If prompt text is not provided but prompt_id is, it attempts to fetch the prompt from the user's collection.

    Args:
        user_id: ID of the user initiating the workflow.
        transcription_id: ID of the transcription to analyze.
        prompt: The custom prompt provided by the user (can be None if prompt_id is given).
        prompt_id: Optional ID of the saved UserPrompt used.

    Returns:
        The ID of the created LLMOperation record.

    Raises:
        PermissionDeniedError: If user lacks permission.
        UsageLimitExceededError: If user exceeds workflow limits.
        TranscriptionNotFoundError: If the transcription doesn't exist or isn't finished.
        InvalidPromptError: If the prompt is invalid (e.g., too long, or ID not found).
        WorkflowInProgressError: If a workflow is already processing (based on LLMOperation status).
        WorkflowError: For other validation or setup errors.
    """
    logger = get_logger(__name__, user_id=user_id, job_id=transcription_id, component="WorkflowService")
    logger.debug(f"Workflow initiation request received. Prompt Text Provided: {bool(prompt)}, Prompt ID: {prompt_id}")
    operation_id: Optional[int] = None
    resolved_prompt_text: Optional[str] = prompt.strip() if prompt else None

    with current_app.app_context():
        user = user_model.get_user_by_id(user_id)
        if not user:
            raise WorkflowError("User not found.")

        if not check_permission(user, 'allow_workflows'):
            logger.warning("Permission denied for workflows.")
            raise PermissionDeniedError("You do not have permission to run workflows.")

        transcription = transcription_model.get_transcription_by_id(transcription_id, user_id)
        if not transcription:
            logger.warning("Transcription not found or not owned by user.")
            raise TranscriptionNotFoundError("Transcription not found or access denied.")
        if transcription.get('status') != 'finished':
            logger.warning(f"Cannot run workflow on non-finished transcription (status: {transcription.get('status')}).")
            raise WorkflowError("Workflows can only be run on finished transcriptions.")

        cursor = get_cursor()
        cursor.execute(
            "SELECT id FROM llm_operations WHERE transcription_id = %s AND status IN ('pending', 'processing')",
            (transcription_id,)
        )
        existing_op = cursor.fetchone()
        if existing_op:
             logger.warning(f"An LLM operation (ID: {existing_op['id']}) is already pending/processing for this transcription.")
             raise WorkflowInProgressError("A workflow is already processing for this transcription.")

        transcript_text = transcription.get('transcription_text')
        if not transcript_text:
            logger.warning("Transcription text is empty.")
            raise WorkflowError("Cannot run workflow on an empty transcript.")

        # --- MODIFIED: Resolve prompt text from user's prompts only ---
        if not resolved_prompt_text and prompt_id is not None:
            logger.debug(f"Prompt text not provided, attempting to fetch using user prompt_id: {prompt_id}")
            user_prompt_obj = user_prompt_model.get_prompt_by_id(prompt_id, user_id)
            if user_prompt_obj:
                resolved_prompt_text = user_prompt_obj.prompt_text
                logger.debug(f"Resolved prompt from UserPrompt ID {prompt_id}.")
            else:
                logger.warning(f"Prompt ID {prompt_id} provided, but no matching prompt found in user's collection.")
                raise InvalidPromptError(f"Workflow prompt with ID {prompt_id} not found.")
        # --- END MODIFIED ---

        if not resolved_prompt_text or not resolved_prompt_text.strip():
             raise InvalidPromptError("Workflow prompt cannot be empty.")

        word_count = len(resolved_prompt_text.split())
        if word_count > 120:
            logger.warning(f"Prompt exceeds 120 words ({word_count}).")
            raise InvalidPromptError("Prompt cannot exceed 120 words.")

        logger.debug("Checking usage limits with is_workflow=True")
        allowed, reason = check_usage_limits(user, is_workflow=True)
        if not allowed:
            logger.warning(f"Workflow usage limit check failed: {reason}")
            raise UsageLimitExceededError(reason)
        logger.debug("Workflow usage limits check passed.")

        llm_provider = current_app.config['WORKFLOW_LLM_PROVIDER']
        llm_model = current_app.config['WORKFLOW_LLM_MODEL']
        logger.info(f"Using configured workflow LLM provider: {llm_provider} ({llm_model})")

        try:
            operation_id = llm_operation_model.create_llm_operation(
                user_id=user_id,
                provider=llm_provider,
                operation_type='workflow',
                input_text=resolved_prompt_text,
                transcription_id=transcription_id,
                prompt_id=prompt_id,
                status='pending'
            )
            if not operation_id:
                raise WorkflowError("Failed to create workflow operation record in database.")
            logger.info(f"Created LLM Operation record ID: {operation_id}", extra={'llm_op_id': operation_id})

            app_instance = current_app._get_current_object()

            thread = threading.Thread(
                target=process_workflow_background,
                args=(
                    app_instance, user_id, transcription_id, operation_id,
                    resolved_prompt_text, transcript_text
                ),
                daemon=True
            )
            thread.start()
            logger.debug("Background workflow thread initiated.")
            return operation_id

        except Exception as e:
            logger.error(f"Failed to start background workflow thread: {e}", exc_info=True)
            if operation_id:
                try:
                    llm_operation_model.update_llm_operation_status(
                        operation_id, status='error', error="Failed to start workflow process."
                    )
                except Exception as db_err:
                     logger.error(f"CRITICAL: Failed to update LLM operation status after startup error: {db_err}", extra={'llm_op_id': operation_id})
            raise WorkflowError("Failed to start workflow process.")


def process_workflow_background(
    app: Flask,
    user_id: int,
    transcription_id: str,
    operation_id: int,
    prompt: str,
    transcript_text: str
) -> None:
    """
    The background task that interacts with the LLM API via llm_service.
    Updates the LLMOperation record with status and results.
    Establishes its own application context.

    Args:
        app: The Flask application instance.
        user_id: ID of the user.
        transcription_id: ID of the transcription.
        operation_id: ID of the LLMOperation record tracking this task.
        prompt: The resolved user prompt text.
        transcript_text: The transcription text.
    """
    logger = get_logger(__name__, user_id=user_id, job_id=transcription_id, llm_op_id=operation_id, component="WorkflowServiceBG")
    result_text: Optional[str] = None
    error_message: Optional[str] = None
    final_status: str = 'error'

    with app.app_context():
        llm_provider = current_app.config['WORKFLOW_LLM_PROVIDER']
        llm_model = current_app.config['WORKFLOW_LLM_MODEL']
        logger.info(f"Background workflow process started using {llm_provider} ({llm_model}).")

        try:
            update_success = llm_operation_model.update_llm_operation_status(operation_id, status='processing')
            if not update_success:
                logger.warning("Failed to update LLM operation status to 'processing'. Record might be missing.")
            logger.debug("Calling LLM service...")
            start_time = time.time()
            user_request_prompt = prompt if prompt is not None else "[No prompt provided]"
            combined_input = f"User Request:\n{user_request_prompt}\n\nTranscript:\n---\n{transcript_text}\n---\n\nAnalysis Result:"
            max_tokens = current_app.config.get('WORKFLOW_MAX_OUTPUT_TOKENS', 1024)

            result_text = llm_service.generate_text_via_llm(
                provider_name=llm_provider,
                model=llm_model,
                user_id=user_id,
                prompt=combined_input,
                max_tokens=max_tokens,
                operation_id=operation_id,
                operation_type='workflow'
            )
            duration = time.time() - start_time
            logger.info(f"LLM service call successful. Duration: {duration:.2f}s")

            if result_text is not None:
                result_text = result_text.strip()
                final_status = 'finished'
                logger.debug("Workflow generation successful.")

                try:
                    role_model.increment_workflow_usage(user_id)
                    logger.debug("Workflow usage incremented.")
                except Exception as usage_err:
                     logger.error(f"Failed to increment workflow usage: {usage_err}", exc_info=True)
            else:
                error_message = "Workflow completed but no result text was generated by the LLM."
                final_status = 'error'
                logger.warning(error_message)


        except (LlmApiError, llm_service.LlmServiceError, ValueError) as e:
            logger.error(f"Error during LLM processing: {e}", exc_info=True)
            error_message = str(e)
            final_status = 'error'
        except Exception as e:
            logger.error(f"Unexpected error during background workflow processing: {e}", exc_info=True)
            error_message = f"An unexpected error occurred: {e}"
            final_status = 'error'

        try:
            llm_operation_model.update_llm_operation_status(
                operation_id=operation_id,
                status=final_status,
                result=result_text,
                error=error_message
            )
            logger.debug(f"LLM Operation record {operation_id} updated to status '{final_status}'.")
        except Exception as db_update_err:
             logger.error(f"CRITICAL: Failed to update final LLM operation status in DB: {db_update_err}", exc_info=True)

        try:
            now_utc_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            cursor = get_cursor()
            sql = """
                  UPDATE transcriptions
                  SET llm_operation_id = %s,
                      llm_operation_status = %s,
                      llm_operation_result = %s,
                      llm_operation_error = %s,
                      llm_operation_ran_at = %s
                  WHERE id = %s
                  """
            cursor.execute(sql, (operation_id, final_status, result_text, error_message, now_utc_iso, transcription_id))
            get_db().commit()
            logger.debug(f"Updated transcription {transcription_id} with LLM operation ID {operation_id} and status '{final_status}'.")
        except Exception as update_err:
            logger.error(f"Failed to update transcription record with LLM operation ID: {update_err}", exc_info=True)

        logger.debug("Background workflow process finished.")


def edit_workflow_result(user_id: int, operation_id: int, new_result: str) -> None:
    """
    Allows a user to edit the generated workflow result stored in the LLMOperation record.

    Args:
        user_id: ID of the user making the edit.
        operation_id: ID of the LLMOperation record to edit.
        new_result: The new text for the workflow result.

    Raises:
        OperationNotFoundError: If the operation doesn't exist or isn't owned.
        WorkflowError: If the update fails for other reasons.
    """
    logger = get_logger(__name__, user_id=user_id, llm_op_id=operation_id, component="WorkflowService")
    logger.debug("Request to edit workflow result.")

    with current_app.app_context():
        try:
            success = llm_operation_model.update_llm_operation_result(
                operation_id=operation_id,
                user_id=user_id,
                new_result=new_result
            )

            if not success:
                logger.error(f"Update failed: LLM Operation record {operation_id} not found or not owned during update.")
                raise OperationNotFoundError("Failed to update workflow result (record not found or permission issue).")
            else:
                logger.debug("Workflow result updated successfully.")

        except MySQLError as db_err:
            logger.error(f"Database error updating LLM operation result: {db_err}", exc_info=True)
            raise WorkflowError("Database error updating workflow result.") from db_err
        except OperationNotFoundError as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error updating LLM operation result: {e}", exc_info=True)
            if isinstance(e, WorkflowError):
                raise e
            else:
                raise WorkflowError("Unexpected error updating workflow result.") from e


def delete_workflow_result(user_id: int, transcription_id: str) -> None:
    """
    Deletes LLMOperation records associated with a transcription's workflow.

    Args:
        user_id: ID of the user requesting deletion.
        transcription_id: ID of the transcription.

    Raises:
        TranscriptionNotFoundError: If the transcription doesn't exist or isn't owned.
        WorkflowError: For database or unexpected errors.
    """
    logger = get_logger(__name__, user_id=user_id, job_id=transcription_id, component="WorkflowService")
    logger.debug("Request to delete workflow result(s).")

    with current_app.app_context():
        transcription = transcription_model.get_transcription_by_id(transcription_id, user_id)
        if not transcription:
            raise TranscriptionNotFoundError("Transcription not found or access denied.")

        deleted_count = 0
        try:
            cursor = get_cursor()
            sql = "DELETE FROM llm_operations WHERE transcription_id = %s AND user_id = %s AND operation_type = 'workflow'"
            cursor.execute(sql, (transcription_id, user_id))
            deleted_count = cursor.rowcount
            get_db().commit()
            logger.info(f"Deleted {deleted_count} workflow LLM operation record(s) for transcription {transcription_id}.")

            if deleted_count > 0 or transcription.get('llm_operation_id') is not None:
                update_sql = """
                    UPDATE transcriptions
                    SET llm_operation_id = NULL,
                        llm_operation_status = NULL,
                        llm_operation_result = NULL,
                        llm_operation_error = NULL,
                        llm_operation_ran_at = NULL
                    WHERE id = %s AND user_id = %s
                """
                cursor.execute(update_sql, (transcription_id, user_id))
                get_db().commit()
                logger.info(f"Cleared workflow fields from transcription record {transcription_id}.")

        except MySQLError as db_err:
            logger.error(f"Database error deleting workflow operations: {db_err}", exc_info=True)
            raise WorkflowError("Database error deleting workflow result(s).") from db_err
        except Exception as e:
            logger.error(f"Unexpected error deleting workflow operations: {e}", exc_info=True)
            raise WorkflowError("Unexpected error deleting workflow result(s).") from e