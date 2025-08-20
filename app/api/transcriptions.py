# app/api/transcriptions.py
# Defines the Blueprint for transcription-related API endpoints.

import os
import uuid
import threading
import logging
import json
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

# Import Flask-Login decorators and current_user proxy
from flask_login import login_required, current_user

# Import application components
from app.config import Config
from app.services import transcription_service, file_service, user_service, pricing_service
from app.models import transcription as transcription_model
from app.models import user as user_model
from app.models.user import User # For type hinting
from app.services.user_service import MissingApiKeyError
from app.services.api_clients.exceptions import TranscriptionApiError
from app.core.decorators import check_permission, check_usage_limits
from app.extensions import limiter
from mysql.connector import Error as MySQLError
# --- ADDED: Import Optional ---
from typing import Optional
# --- END ADDED ---


# Define the Blueprint
transcriptions_bp = Blueprint('transcriptions', __name__, url_prefix='/api')

# --- Transcription Job Endpoints ---

@transcriptions_bp.route('/transcribe', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def transcribe_audio():
    """
    API endpoint to upload an audio file and initiate a transcription job.
    Handles file validation (size, usage limits), saving, metadata extraction,
    creating the initial DB record, and starting the background task.
    Calculates duration in minutes.
    Accepts pending workflow information including the original prompt ID.
    """
    user: User = current_user
    user_id = user.id
    log_prefix = f"[API:Transcribe:User:{user_id}]"
    logging.debug(f"{log_prefix} /transcribe request received.")

    if 'audio_file' not in request.files:
        logging.error(f"{log_prefix} No 'audio_file' part in the request.")
        return jsonify({'error': 'No audio file part in the request.'}), 400
    file = request.files['audio_file']
    if file.filename == '':
        logging.error(f"{log_prefix} No file selected for upload.")
        return jsonify({'error': 'No selected file.'}), 400
    if not file_service.allowed_file(file.filename):
        logging.error(f"{log_prefix} File type not allowed: {file.filename}")
        return jsonify({'error': 'File type not allowed.'}), 400

    original_filename = secure_filename(file.filename)
    job_id = str(uuid.uuid4())
    short_job_id = job_id[:8]
    job_log_prefix = f"[JOB:{short_job_id}:User:{user_id}]"

    upload_dir = current_app.config['TEMP_UPLOADS_DIR']
    temp_filename = os.path.join(upload_dir, f"{job_id}_{original_filename}")

    file_size_mb = 0.0
    audio_length_minutes = 0.0

    try:
        os.makedirs(upload_dir, exist_ok=True)
        if not file_service.validate_file_path(temp_filename, upload_dir):
             logging.error(f"{job_log_prefix} Invalid temporary file path generated: {temp_filename}")
             raise PermissionError("Invalid file path.")

        file.save(temp_filename)
        file_size_bytes = os.path.getsize(temp_filename)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
        logging.info(f"{job_log_prefix} Saved temp upload: {os.path.basename(temp_filename)} (Size: {file_size_mb:.2f} MB)")

        max_size_mb = current_app.config.get('MAX_FILE_SIZE_MB', 1024)
        if file_size_mb > max_size_mb:
             logging.warning(f"{job_log_prefix} File size {file_size_mb:.2f}MB exceeds limit {max_size_mb}MB.")
             file_service.remove_files([temp_filename])
             return jsonify({'error': f'File exceeds size limit ({max_size_mb}MB)', 'code': 'SIZE_LIMIT_EXCEEDED'}), 413

        try:
            # Use the memory-efficient ffprobe method to get duration
            audio_length_seconds, audio_length_minutes = file_service.get_audio_duration(temp_filename)
            if audio_length_seconds == 0.0:
                logging.warning(f"{job_log_prefix} Could not determine audio duration for '{os.path.basename(temp_filename)}'. Assuming 0 minutes.")
        except Exception as audio_err:
            logging.error(f"{job_log_prefix} Error getting audio duration for '{os.path.basename(temp_filename)}': {audio_err}", exc_info=True)
            audio_length_seconds = 0.0
            audio_length_minutes = 0.0

    except Exception as e:
        logging.exception(f"{job_log_prefix} Failed during file save or metadata extraction: {e}")
        if os.path.exists(temp_filename):
            file_service.remove_files([temp_filename])
        return jsonify({'error': 'Failed to save or process uploaded file.'}), 500

    try:
        language_code = request.form.get('language_code', current_app.config['DEFAULT_LANGUAGE'])
        api_choice = request.form.get('api_choice', current_app.config['DEFAULT_TRANSCRIPTION_PROVIDER'])
        context_prompt = request.form.get('context_prompt', '')
        pending_workflow_prompt_text = request.form.get('pending_workflow_prompt_text')
        pending_workflow_prompt_title = request.form.get('pending_workflow_prompt_title')
        pending_workflow_prompt_color = request.form.get('pending_workflow_prompt_color')
        pending_workflow_origin_prompt_id_str = request.form.get('pending_workflow_origin_prompt_id')
        parsed_pending_workflow_origin_id: Optional[int] = None
        if pending_workflow_origin_prompt_id_str:
            try:
                parsed_pending_workflow_origin_id = int(pending_workflow_origin_prompt_id_str)
            except (ValueError, TypeError): # Added TypeError
                logging.warning(f"{job_log_prefix} Invalid pending_workflow_origin_prompt_id received: '{pending_workflow_origin_prompt_id_str}'. Ignoring.")
        
        logging.debug(f"{job_log_prefix} Params - API: {api_choice}, Lang: {language_code}, Context: {'Yes' if context_prompt else 'No'}, Pending WF Text: {'Set' if pending_workflow_prompt_text else 'Not Set'}, Pending WF Origin ID: {parsed_pending_workflow_origin_id}")


        if api_choice not in current_app.config['TRANSCRIPTION_PROVIDERS']:
             logging.error(f"{job_log_prefix} Invalid API choice '{api_choice}'. Allowed: {current_app.config['TRANSCRIPTION_PROVIDERS']}")
             raise ValueError(f"Invalid transcription provider selected: {api_choice}")

        price = pricing_service.get_price(item_type='transcription', item_key=api_choice)
        cost_to_add = 0.0
        if price is not None:
            cost_to_add = price * (audio_length_minutes if audio_length_minutes >= 1 else audio_length_seconds / 60)

        allowed, reason = check_usage_limits(user, cost_to_add=cost_to_add, minutes_to_add=audio_length_minutes)
        if not allowed:
            logging.warning(f"{job_log_prefix} Usage limit check failed: {reason}")
            file_service.remove_files([temp_filename])
            return jsonify({'error': reason, 'code': 'USAGE_LIMIT_EXCEEDED'}), 403
        logging.debug(f"{job_log_prefix} Usage limit check passed.")

        context_prompt_used_flag = False
        if context_prompt:
            if check_permission(user, 'allow_context_prompt'):
                context_prompt_used_flag = True
            else:
                logging.warning(f"{job_log_prefix} User provided context prompt but lacks permission. Prompt will be ignored.")
                context_prompt = ""

        try:
            # --- MODIFIED: Pass parsed_pending_workflow_origin_id to create_transcription_job ---
            transcription_model.create_transcription_job(
                job_id=job_id,
                user_id=user_id,
                filename=original_filename,
                api_used=api_choice,
                file_size_mb=file_size_mb,
                audio_length_minutes=audio_length_minutes,
                context_prompt_used=context_prompt_used_flag,
                pending_workflow_prompt_text=pending_workflow_prompt_text if pending_workflow_prompt_text else None,
                pending_workflow_prompt_title=pending_workflow_prompt_title if pending_workflow_prompt_title else None,
                pending_workflow_prompt_color=pending_workflow_prompt_color if pending_workflow_prompt_color else None,
                pending_workflow_origin_prompt_id=parsed_pending_workflow_origin_id # Pass the ID
            )
            # --- END MODIFIED ---
            logging.info(f"{job_log_prefix} Created initial job record in database (Context Used: {context_prompt_used_flag}).")
        except MySQLError as db_create_err:
            logging.error(f"{job_log_prefix} Failed to create initial job record in DB: {db_create_err}", exc_info=True)
            file_service.remove_files([temp_filename])
            return jsonify({'error': 'Failed to initialize transcription job.'}), 500
        except Exception as db_create_err:
            logging.error(f"{job_log_prefix} Unexpected error creating initial job record in DB: {db_create_err}", exc_info=True)
            file_service.remove_files([temp_filename])
            return jsonify({'error': 'Failed to initialize transcription job.'}), 500

        app_instance = current_app._get_current_object()

        thread = threading.Thread(
            target=transcription_service.process_transcription,
            args=(
                app_instance,
                job_id,
                user_id,
                temp_filename,
                language_code,
                api_choice,
                original_filename,
                context_prompt,
                pending_workflow_prompt_text,
                pending_workflow_prompt_title,
                pending_workflow_prompt_color,
                parsed_pending_workflow_origin_id # Already passed here
            ),
            daemon=True
        )
        thread.start()
        logging.info(f"{job_log_prefix} Background transcription thread initiated.")

        return jsonify({
            'job_id': job_id,
            'message': 'Transcription job started successfully.',
            'audio_length_minutes': audio_length_minutes
        }), 202

    except (PermissionError, MissingApiKeyError, ValueError) as e:
         logging.error(f"{job_log_prefix} Failed to initiate transcription due to pre-check failure: {e}")
         file_service.remove_files([temp_filename])
         try:
             with current_app.app_context():
                 transcription_model.set_job_error(job_id, f"Initialization failed: {str(e)}")
         except Exception as db_err:
             logging.error(f"{job_log_prefix} Failed to set error status after initialization failure: {db_err}")
         status_code = 403 if isinstance(e, (PermissionError, MissingApiKeyError)) else 400
         return jsonify({'error': str(e)}), status_code
    except Exception as e:
        logging.exception(f"{job_log_prefix} Error initiating transcription job: {e}")
        file_service.remove_files([temp_filename])
        try:
             with current_app.app_context():
                 transcription_model.set_job_error(job_id, f"Initialization failed: {str(e)}")
        except Exception as db_err:
             logging.error(f"{job_log_prefix} Failed to set error status after initialization failure: {db_err}")
        return jsonify({'error': 'Failed to start transcription job due to an internal error.'}), 500


@transcriptions_bp.route('/progress/<job_id>', methods=['GET'])
@login_required
@limiter.exempt
def get_progress(job_id):
    """
    API endpoint to poll for transcription job progress and results.
    Ensures the requesting user owns the job.
    NOTE: This endpoint now ONLY returns transcription status.
          LLM/Workflow status must be polled separately if needed.
    Includes a flag indicating if title polling should occur.
    Includes pending workflow details if the job is finished.
    """
    user_id = current_user.id
    short_job_id = job_id[:8] if job_id else 'invalid'
    log_prefix = f"[API:Progress:JOB:{short_job_id}:User:{user_id}]"

    try:
        job_data = transcription_model.get_transcription_by_id(job_id, user_id)

        if not job_data:
            unowned_job = transcription_model.get_transcription_by_id(job_id)
            if unowned_job:
                logging.warning(f"{log_prefix} Access denied: Job exists but is not owned by user.")
                return jsonify({'error': 'Access denied to this job.'}), 403
            else:
                logging.warning(f"{log_prefix} Job not found.")
                return jsonify({'error': 'Job not found.'}), 404

        status = job_data.get('status', 'unknown')
        is_finished = status in ('finished', 'error', 'cancelled')
        is_error = status == 'error'
        is_cancelled = status == 'cancelled'

        progress_log = []
        raw_log = job_data.get('progress_log')
        if isinstance(raw_log, list):
            progress_log = raw_log
        elif raw_log:
            logging.warning(f"{log_prefix} Progress log from DB is not a list. Type: {type(raw_log)}. Content: {raw_log}")
            progress_log = ["Error: Invalid progress log format."]

        should_poll_title = False
        if status == 'finished':
            user = user_model.get_user_by_id(user_id)
            if user and user.enable_auto_title_generation and user.has_permission('allow_auto_title_generation'):
                title_status = job_data.get('title_generation_status', 'pending')
                if title_status in ['pending', 'processing']:
                    should_poll_title = True

        response_data = {
            'job_id': job_id,
            'status': status,
            'progress': progress_log,
            'finished': is_finished,
            'error_message': job_data.get('error_message') if is_error else None,
            'result': None, # This will be populated below if finished successfully
            'file_size_mb': job_data.get('file_size_mb', 0.0),
            'audio_length_minutes': job_data.get('audio_length_minutes', 0.0),
            'api_used': job_data.get('api_used', 'unknown'),
            'filename': job_data.get('filename', 'unknown'),
            'should_poll_title': should_poll_title,
            '_llm_status_note': 'LLM/Workflow status must be polled separately.'
        }

        if is_finished and not is_error and not is_cancelled:
            response_data['result'] = {
                'id': job_data['id'],
                'filename': job_data.get('filename'),
                'detected_language': job_data.get('detected_language'),
                'transcription_text': job_data.get('transcription_text'),
                'api_used': job_data.get('api_used'),
                'created_at': job_data.get('created_at'),
                'status': status,
                'audio_length_minutes': job_data.get('audio_length_minutes', 0.0),
                'generated_title': job_data.get('generated_title'),
                'title_generation_status': job_data.get('title_generation_status', 'pending'),
                'pending_workflow_prompt_text': job_data.get('pending_workflow_prompt_text'),
                'pending_workflow_prompt_title': job_data.get('pending_workflow_prompt_title'),
                'pending_workflow_prompt_color': job_data.get('pending_workflow_prompt_color'),
                # --- MODIFIED: Include pending_workflow_origin_prompt_id in response ---
                'pending_workflow_origin_prompt_id': job_data.get('pending_workflow_origin_prompt_id')
                # --- END MODIFIED ---
            }
            logging.debug(f"{log_prefix} Job finished successfully, returning result. Should poll title: {should_poll_title}")
        elif is_error:
            logging.debug(f"{log_prefix} Job finished with error.")
        elif is_cancelled:
            logging.debug(f"{log_prefix} Job was cancelled.")

        return jsonify(response_data), 200

    except Exception as e:
        logging.exception(f"{log_prefix} Unexpected error fetching progress:")
        return jsonify({'error': 'Internal server error fetching job progress.'}), 500

@transcriptions_bp.route('/transcribe/<job_id>', methods=['DELETE'])
@login_required
def cancel_transcription(job_id):
    """
    API endpoint to request cancellation of an ongoing transcription job.
    Updates the job status to 'cancelling' to signal the background thread.
    """
    user_id = current_user.id
    short_job_id = job_id[:8] if job_id else 'invalid'
    log_prefix = f"[API:Cancel:JOB:{short_job_id}:User:{user_id}]"
    logging.debug(f"{log_prefix} Cancellation request received.")

    try:
        job_data = transcription_model.get_transcription_by_id(job_id, user_id)

        if not job_data:
            unowned_job = transcription_model.get_transcription_by_id(job_id)
            if unowned_job:
                logging.warning(f"{log_prefix} Access denied: Job exists but is not owned by user.")
                return jsonify({'error': 'Access denied to this job.'}), 403
            else:
                logging.warning(f"{log_prefix} Job not found.")
                return jsonify({'error': 'Job not found.'}), 404

        current_status = job_data.get('status')
        if current_status not in ['pending', 'processing']:
            logging.warning(f"{log_prefix} Cannot cancel job with status '{current_status}'.")
            return jsonify({'error': f'Job cannot be cancelled (status: {current_status}).'}), 400

        transcription_model.update_job_status(job_id, 'cancelling')
        transcription_model.update_job_progress(job_id, "Cancellation requested by user.")

        logging.info(f"{log_prefix} Job status updated to 'cancelling'. Background thread will terminate.")
        return jsonify({'message': 'Transcription cancellation requested.'}), 200

    except Exception as e:
        logging.exception(f"{log_prefix} Unexpected error requesting cancellation:")
        return jsonify({'error': 'Internal server error requesting cancellation.'}), 500

@transcriptions_bp.route('/transcriptions', methods=['GET'])
@login_required
def get_transcriptions():
    """
    API endpoint to get the list of the logged-in user's transcription history.
    Respects history limits defined by the user's role.
    NOTE: Returns only transcription data. Associated LLM data must be fetched separately if needed.
    """
    user: User = current_user
    user_id = user.id
    log_prefix = f"[API:History:User:{user_id}]"
    logging.debug(f"{log_prefix} /transcriptions GET request received.")

    try:
        limit = user.get_limit('max_history_items') if user.role else 0
        logging.debug(f"{log_prefix} Applying history limit: {'Unlimited' if limit <= 0 else limit}")

        transcriptions = transcription_model.get_all_transcriptions(user_id, limit=limit)

        logging.info(f"{log_prefix} Retrieved {len(transcriptions)} transcription records.")
        return jsonify(transcriptions), 200
    except Exception as e:
        logging.exception(f"{log_prefix} Error fetching transcription history:")
        return jsonify({'error': 'Failed to retrieve transcription history.'}), 500

@transcriptions_bp.route('/transcriptions/<transcription_id>', methods=['DELETE'])
@login_required
def delete_transcription(transcription_id):
    """
    API endpoint to delete a specific transcription record owned by the user.
    The service layer handles deletion of associated workflow results (LLM operations).
    """
    user_id = current_user.id
    short_job_id = transcription_id[:8] if transcription_id else 'invalid'
    log_prefix = f"[API:Delete:JOB:{short_job_id}:User:{user_id}]"
    logging.debug(f"{log_prefix} /transcriptions DELETE request received.")

    try:
        from app.services import workflow_service
        try:
            workflow_service.delete_workflow_result(user_id, transcription_id)
            logging.info(f"{log_prefix} Associated workflow LLM operation(s) cleared (if existed).")
        except workflow_service.TranscriptionNotFoundError:
            pass
        except Exception as wf_del_err:
            logging.error(f"{log_prefix} Error clearing workflow result during transcription delete: {wf_del_err}", exc_info=True)

        success = transcription_model.delete_transcription(transcription_id, user_id)
        if success:
            logging.info(f"{log_prefix} Transcription soft-deleted successfully.")
            return jsonify({'message': 'Transcription deleted successfully'}), 200
        else:
            exists_check = transcription_model.get_transcription_by_id(transcription_id)
            if exists_check:
                logging.warning(f"{log_prefix} Delete failed due to ownership mismatch.")
                return jsonify({'error': 'Forbidden: You do not own this transcription.'}), 403
            else:
                logging.warning(f"{log_prefix} Delete failed: Transcription not found.")
                return jsonify({'error': 'Transcription not found.'}), 404
    except Exception as e:
        logging.exception(f"{log_prefix} Error deleting transcription:")
        return jsonify({'error': 'Failed to delete transcription due to an internal error.'}), 500

@transcriptions_bp.route('/transcriptions/clear', methods=['DELETE'])
@login_required
def clear_transcriptions():
    """
    API endpoint to delete all transcription records for the logged-in user.
    The service layer handles deletion of associated workflow results (LLM operations).
    """
    user_id = current_user.id
    log_prefix = f"[API:Clear:User:{user_id}]"
    logging.warning(f"{log_prefix} /transcriptions/clear DELETE request received.")

    try:
        from app.services import workflow_service
        all_user_transcriptions = transcription_model.get_all_transcriptions(user_id, limit=None)
        cleared_workflows = 0
        for t in all_user_transcriptions:
            try:
                workflow_service.delete_workflow_result(user_id, t['id'])
                cleared_workflows += 1
            except Exception as wf_clear_err:
                logging.error(f"{log_prefix} Error clearing workflow ops for job {t['id']} during clear all: {wf_clear_err}")
        logging.info(f"{log_prefix} Attempted to clear associated workflow LLM operation(s) for {cleared_workflows} transcriptions.")

        deleted_count = transcription_model.clear_transcriptions(user_id)
        logging.info(f"{log_prefix} {deleted_count} transcriptions soft-deleted successfully.")
        return jsonify({'message': f'All {deleted_count} transcriptions cleared successfully.'}), 200
    except Exception as e:
        logging.exception(f"{log_prefix} Error clearing all transcriptions:")
        return jsonify({'error': 'Failed to clear all transcriptions due to an internal error.'}), 500

@transcriptions_bp.route('/transcriptions/<transcription_id>/log_download', methods=['POST'])
@login_required
def log_download(transcription_id):
    """
    API endpoint to mark a transcription as downloaded.
    """
    user_id = current_user.id
    short_job_id = transcription_id[:8] if transcription_id else 'invalid'
    log_prefix = f"[API:LogDownload:JOB:{short_job_id}:User:{user_id}]"
    logging.debug(f"{log_prefix} Request received to log download.")

    if not check_permission(current_user, 'allow_download_transcript'):
        logging.warning(f"{log_prefix} Download log failed: User lacks 'allow_download_transcript' permission.")
        return jsonify({'error': 'Permission denied to download transcripts.'}), 403

    try:
        success = transcription_model.mark_transcription_as_downloaded(transcription_id, user_id)
        if success:
            logging.info(f"{log_prefix} Download logged successfully.")
            return jsonify({'message': 'Download logged successfully'}), 200
        else:
            job_data = transcription_model.get_transcription_by_id(transcription_id)
            if not job_data:
                logging.warning(f"{log_prefix} Download log failed: Job not found.")
                return jsonify({'error': 'Transcription not found.'}), 404
            elif job_data.get('user_id') != user_id:
                logging.warning(f"{log_prefix} Download log failed: Ownership mismatch.")
                return jsonify({'error': 'Forbidden: You do not own this transcription.'}), 403
            elif job_data.get('status') != 'finished':
                logging.warning(f"{log_prefix} Download log failed: Job status is '{job_data.get('status')}'.")
                return jsonify({'error': 'Cannot log download for a non-finished job.'}), 400
            else:
                logging.warning(f"{log_prefix} Download log failed for unknown reason (model returned False).")
                return jsonify({'error': 'Failed to log download.'}), 500
    except Exception as e:
        logging.exception(f"{log_prefix} Error logging download:")
        return jsonify({'error': 'Failed to log download due to an internal error.'}), 500

@transcriptions_bp.route('/transcriptions/<transcription_id>/title', methods=['GET'])
@login_required
def get_title_status(transcription_id):
    """
    API endpoint to get the status and generated title for a transcription.
    Used by the frontend to poll for title updates.
    """
    user_id = current_user.id
    short_job_id = transcription_id[:8] if transcription_id else 'invalid'
    log_prefix = f"[API:TitleStatus:JOB:{short_job_id}:User:{user_id}]"

    try:
        job_data = transcription_model.get_transcription_by_id(transcription_id, user_id)

        if not job_data:
            unowned_job = transcription_model.get_transcription_by_id(transcription_id)
            if unowned_job:
                logging.warning(f"{log_prefix} Access denied: Job exists but is not owned by user.")
                return jsonify({'error': 'Access denied to this job.'}), 403
            else:
                logging.warning(f"{log_prefix} Job not found.")
                return jsonify({'error': 'Job not found.'}), 404

        title_status = job_data.get('title_generation_status', 'pending')
        generated_title = job_data.get('generated_title')
        filename = job_data.get('filename', 'Unknown Filename')

        response_data = {}
        if title_status == 'success' and generated_title:
            response_data = {'title': generated_title, 'status': 'generated'}
        elif title_status == 'failed':
            response_data = {'title': filename, 'status': 'failed'}
        elif title_status == 'processing':
            response_data = {'title': filename, 'status': 'processing'}
        elif title_status == 'pending':
            response_data = {'title': filename, 'status': 'pending'}
        # --- MODIFIED: Add case for 'disabled' status ---
        elif title_status == 'disabled':
            response_data = {'title': filename, 'status': 'disabled'}
        # --- END MODIFIED ---
        else:
            logging.error(f"{log_prefix} Unknown title generation status found: {title_status}")
            response_data = {'title': filename, 'status': 'unknown'}

        return jsonify(response_data), 200

    except Exception as e:
        logging.exception(f"{log_prefix} Unexpected error fetching title status:")
        return jsonify({'error': 'Internal server error fetching title status.'}), 500

@transcriptions_bp.route('/transcriptions/<transcription_id>/workflow-details', methods=['GET'])
@login_required
def get_workflow_details_for_transcription(transcription_id: str):
    """
    API endpoint to get the LLM operation details linked to a transcription.
    Used by the frontend to initiate workflow polling for pre-applied workflows.
    """
    user_id = current_user.id
    short_job_id = transcription_id[:8] if transcription_id else 'invalid'
    log_prefix = f"[API:WFDetails:JOB:{short_job_id}:User:{user_id}]"
    logging.debug(f"{log_prefix} Request received for workflow details.")

    try:
        job_data = transcription_model.get_transcription_by_id(transcription_id, user_id)

        if not job_data:
            unowned_job = transcription_model.get_transcription_by_id(transcription_id)
            if unowned_job:
                logging.warning(f"{log_prefix} Access denied: Job exists but is not owned by user.")
                return jsonify({'error': 'Access denied to this job.'}), 403
            else:
                logging.warning(f"{log_prefix} Job not found.")
                return jsonify({'error': 'Job not found.'}), 404

        response_data = {
            'transcription_id': transcription_id,
            'llm_operation_id': job_data.get('llm_operation_id'),
            'llm_operation_status': job_data.get('llm_operation_status'),
            'llm_operation_result': job_data.get('llm_operation_result'),
            'llm_operation_error': job_data.get('llm_operation_error'),
            'llm_operation_ran_at': job_data.get('llm_operation_ran_at'),
            'pending_workflow_prompt_text': job_data.get('pending_workflow_prompt_text'),
            'pending_workflow_prompt_title': job_data.get('pending_workflow_prompt_title'),
            'pending_workflow_prompt_color': job_data.get('pending_workflow_prompt_color'),
            # --- MODIFIED: Include pending_workflow_origin_prompt_id in response ---
            'pending_workflow_origin_prompt_id': job_data.get('pending_workflow_origin_prompt_id')
            # --- END MODIFIED ---
        }
        logging.debug(f"{log_prefix} Returning workflow details: OpID {response_data['llm_operation_id']}, Status {response_data['llm_operation_status']}")
        return jsonify(response_data), 200

    except Exception as e:
        logging.exception(f"{log_prefix} Unexpected error fetching workflow details:")
        return jsonify({'error': 'Internal server error fetching workflow details.'}), 500
