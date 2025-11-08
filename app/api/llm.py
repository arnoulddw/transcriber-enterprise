# app/api/llm.py
# Defines the Blueprint for direct LLM interaction endpoints.

import logging
from typing import Optional
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from flask_babel import gettext as _

# Import services and exceptions
from app.services import llm_service, user_service
from app.services.llm_service import LlmServiceError
from app.services.api_clients.exceptions import LlmApiError, LlmConfigurationError, LlmGenerationError, LlmSafetyError, LlmRateLimitError
from app.services.user_service import MissingApiKeyError
# --- ADDED: Import llm_operation model ---
from app.models import llm_operation as llm_operation_model
# --- END ADDED ---

# Import decorators
from app.core.decorators import permission_required # Add if needed for specific LLM permissions
from app.extensions import limiter

# Define the Blueprint
llm_bp = Blueprint('llm', __name__, url_prefix='/api/llm')


def _compose_error_message(base_message: str, details: Optional[str] = None) -> str:
    """Return a translated error message with optional diagnostic details."""
    details_text = str(details or "").strip()
    if details_text:
        return f"{base_message} {_('Details')}: {details_text}"
    return base_message

# --- Direct LLM Interaction Endpoints (Example) ---

@llm_bp.route('/generate', methods=['POST'])
@login_required
# @permission_required('use_llm_generate') # Add specific permission if needed
# Apply rate limiting (consider a separate limit for direct LLM calls)
# @limiter.limit("...")
def generate_llm_text():
    """
    API endpoint for direct text generation using a configured LLM.
    Expects JSON: {"prompt": "...", "provider": "optional_provider_name", ...}
    """
    user_id = current_user.id
    log_prefix = f"[API:LLM:Generate:User:{user_id}]"
    data = request.get_json()

    if not data or 'prompt' not in data:
        logging.warning(f"{log_prefix} Invalid request: Missing 'prompt' in JSON payload.")
        return jsonify({'error': _('Please include a prompt before requesting AI text generation.')}), 400

    prompt = data['prompt']
    # Use user's default or system default LLM provider
    provider = data.get('provider', current_app.config.get('DEFAULT_LLM_PROVIDER'))
    # Get other potential parameters from request data
    kwargs = {k: v for k, v in data.items() if k not in ['prompt', 'provider']}

    logging.info(f"{log_prefix} Received request for text generation using provider '{provider}'.")

    try:
        # --- Get API Key ---
        # This logic depends on whether LLM keys are global or user-specific
        # Assuming global for now, adjust if user-specific keys are implemented for LLMs
        api_key: Optional[str] = None
        if provider.startswith("gemini"):
            api_key = current_app.config.get('GEMINI_API_KEY')
        elif provider.startswith("openai") or provider.startswith("gpt"):
            api_key = current_app.config.get('OPENAI_API_KEY')
        # Add other providers...

        if not api_key:
             # Check if user has the key if multi-user and user-specific keys are implemented
             # if current_app.config['DEPLOYMENT_MODE'] == 'multi':
             #     key_service_name = ... # Determine key name based on provider
             #     api_key = user_service.get_decrypted_api_key(user_id, key_service_name)
             # if not api_key:
             raise LlmConfigurationError(f"API key for LLM provider '{provider}' is not configured.")

        # --- Call LLM Service ---
        result_text = llm_service.generate_text_via_llm(
            provider_name=provider,
            api_key=api_key,
            prompt=prompt,
            **kwargs
        )

        # TODO: Consider logging this operation in the llm_operations table

        return jsonify({'result': result_text}), 200

    except (LlmConfigurationError, ValueError) as e: # Config/Input errors
        logging.warning(f"{log_prefix} Configuration or Value error: {e}")
        return jsonify({'error': _compose_error_message(_('We could not start the AI request because the configuration or input is invalid.'), str(e))}), 400
    except LlmRateLimitError as e:
        logging.warning(f"{log_prefix} LLM Rate Limit error: {e}")
        return jsonify({'error': _compose_error_message(_('The AI provider temporarily rate-limited this request. Please wait a moment and try again.'), str(e))}), 429
    except LlmSafetyError as e:
        logging.warning(f"{log_prefix} LLM Safety error: {e}")
        return jsonify({'error': _compose_error_message(_('The AI provider blocked this request because of its safety filters. Please adjust your prompt and try again.'), str(e))}), 400 # Bad Request for safety
    except (LlmApiError, LlmServiceError) as e: # API/Service errors
        logging.error(f"{log_prefix} LLM generation failed: {e}", exc_info=True)
        return jsonify({'error': _compose_error_message(_('The AI provider could not complete this request. Please try again later.'), str(e))}), 500 # Internal Server Error or specific code from error
    except Exception as e:
        logging.error(f"{log_prefix} Unexpected error during LLM generation: {e}", exc_info=True)
        return jsonify({'error': _('We encountered an unexpected error while generating text. Please try again.')}), 500

# --- ADDED: LLM Operation Status Endpoint ---
@llm_bp.route('/operations/<int:operation_id>/status', methods=['GET'])
@login_required
def get_llm_operation_status(operation_id: int):
    """
    API endpoint to get the status and result of a specific LLM operation.
    Ensures the requesting user owns the operation.
    """
    user_id = current_user.id
    log_prefix = f"[API:LLM:Status:Op:{operation_id}:User:{user_id}]"
    logging.debug(f"{log_prefix} Request received.")

    try:
        # Fetch the operation, verifying ownership
        operation_data = llm_operation_model.get_llm_operation_by_id(operation_id, user_id)

        if not operation_data:
            # Check if it exists at all to differentiate 404 from 403
            unowned_op = llm_operation_model.get_llm_operation_by_id(operation_id)
            if unowned_op:
                logging.warning(f"{log_prefix} Access denied: Operation exists but is not owned by user.")
                return jsonify({'error': _('You do not have access to this AI operation.')}), 403
            else:
                logging.warning(f"{log_prefix} LLM operation not found.")
                return jsonify({'error': _('We could not find that AI operation.')}), 404

        # Prepare response
        response_data = {
            'operation_id': operation_id,
            'status': operation_data.get('status', 'unknown'),
            'result': operation_data.get('result') if operation_data.get('status') == 'finished' else None,
            'error': operation_data.get('error') if operation_data.get('status') == 'error' else None,
            'provider': operation_data.get('provider'),
            'operation_type': operation_data.get('operation_type'),
            'created_at': operation_data.get('created_at'),
            'completed_at': operation_data.get('completed_at'),
            'transcription_id': operation_data.get('transcription_id'),
            'prompt_id': operation_data.get('prompt_id')
        }
        logging.debug(f"{log_prefix} Returning status: {response_data['status']}")
        return jsonify(response_data), 200

    except Exception as e:
        logging.error(f"{log_prefix} Unexpected error fetching LLM operation status: {e}", exc_info=True)
        return jsonify({'error': _('We encountered an internal error while fetching the AI operation status. Please try again.')}), 500
# --- END ADDED ---

# Add other endpoints like /chat, /embedding as needed
